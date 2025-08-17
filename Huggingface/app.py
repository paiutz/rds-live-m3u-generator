#!/usr/bin/env python3
"""
Flask M3U Auto-Update Service for RDS Live Channels
Provides REST API and web interface for M3U playlist generation with EPG support
Optimized for Hugging Face Spaces deployment
"""

import os
import re
import time
import json
import hashlib
import logging
import threading
import signal
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, send_file, jsonify, render_template_string, request, Response
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Configure logging for Hugging Face
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/m3u_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create logs directory if it doesn't exist
os.makedirs('/app/logs', exist_ok=True)

@dataclass
class Channel:
    """Data class for channel information"""
    id: str
    title: str
    poster: Optional[str]
    link: str
    category: str
    stream_url: Optional[str] = None
    # EPG fields
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    tvg_shift: Optional[str] = "0"
    tvg_chno: Optional[str] = None

@dataclass
class EPGProgram:
    """Data class for EPG program information"""
    channel_id: str
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    category: Optional[str] = None

@dataclass
class ServiceStats:
    """Service statistics"""
    total_updates: int = 0
    last_update: Optional[str] = None
    total_channels: int = 0
    working_streams: int = 0
    failed_streams: int = 0
    last_update_duration: float = 0.0
    epg_programs: int = 0

class Config:
    """Configuration management optimized for Hugging Face"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'your_strong_secret_key_here')
    BASE_URL = 'https://rds.live'
    UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', 600))  # 10 minutes (reduced for HF)
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', 3))  # Reduced for HF resources
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 15))
    CACHE_EXPIRY = int(os.getenv('CACHE_EXPIRY', 300))  # 5 minutes
    PORT = int(os.getenv('PORT', 7860))  # Hugging Face default port
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    EPG_URL = os.getenv('EPG_URL', 'http://epg.iptv.ro/epg.xml')
    EPG_UPDATE_INTERVAL = int(os.getenv('EPG_UPDATE_INTERVAL', 3600))

class RDSLiveM3UGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.session = self._create_session()
        self.category_mapping = {
            'generaliste': 'General',
            'copii': 'Kids',
            'filme': 'Movies',
            'sport': 'Sport',
            'stiri': 'News',
            'muzica': 'Music',
            'documentare': 'Documentary',
            'diverse': 'Various',
            'religioase': 'Religious'
        }
        
        # Cache and stats
        self.last_update = None
        self.last_channels: List[Channel] = []
        self.update_in_progress = False
        self.stats = ServiceStats()
        self.video_cache = {}
        self.epg_cache = {}
        self.m3u_content = ""
        self.epg_content = ""
        self.epg_programs: List[EPGProgram] = []
        self.shutdown_flag = False
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': self.config.BASE_URL,
            'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        })
        return session

    def extract_all_channels(self) -> List[Channel]:
        """Extract all channels from the main page"""
        url = f'{self.config.BASE_URL}/canale-tv-1/'
        
        try:
            response = self.session.get(url, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching channels: {e}")
            return []
        
        response_text = response.text
        lista_canale_match = re.search(r'<div class="lista-canale">(.*?)</div>', response_text, re.DOTALL)
        if not lista_canale_match:
            logger.error("Could not find channels list section")
            return []
        
        lista_canale_html = lista_canale_match.group(1)
        channels = []
        regex_pattern = r'<article id="post-(\d+)" class="(.*?)">(.*?)</article>'
        articles = re.findall(regex_pattern, lista_canale_html, re.DOTALL)
        
        for post_id, article_class, article_content in articles:
            try:
                channel = self._parse_channel(post_id, article_class, article_content)
                if channel:
                    channels.append(channel)
            except Exception as e:
                logger.warning(f"Error processing channel {post_id}: {e}")
                continue
                
        return channels

    def _parse_channel(self, post_id: str, article_class: str, article_content: str) -> Optional[Channel]:
        """Parse a single channel from HTML content"""
        title_match = re.search(r'<a class="post-thumbnail".*?title="(.*?)"', article_content)
        if not title_match:
            return None
        
        title = re.sub(r'\b(online|gratis|HD)\b', '', title_match.group(1), flags=re.IGNORECASE).strip()
        
        link_match = re.search(r'<a class="post-thumbnail".*?href="(.*?)"', article_content)
        link = link_match.group(1).strip() if link_match else ''
        
        poster_match = re.search(r'<source .*?srcset="(.*?)"', article_content)
        if poster_match:
            poster = poster_match.group(1).split()[0].strip()
        else:
            poster_match = re.search(r'data-lazy-src="(.*?)"', article_content)
            if not poster_match:
                poster_match = re.search(r'<img.*?src="(.*?)"', article_content)
            poster = poster_match.group(1).strip() if poster_match else None
            
        if poster and poster.endswith('.webp'):
            poster = poster.replace('.webp', '')
            
        category = self._extract_category_from_class(article_class)
        
        # Generate EPG-related fields
        tvg_id = f"RDS.{post_id}"
        tvg_name = title
        tvg_logo = poster if poster else ""
        tvg_shift = "0"
        tvg_chno = post_id
        
        if title and post_id:
            return Channel(
                id=post_id,
                title=title,
                poster=poster,
                link=link,
                category=category,
                tvg_id=tvg_id,
                tvg_name=tvg_name,
                tvg_logo=tvg_logo,
                tvg_shift=tvg_shift,
                tvg_chno=tvg_chno
            )
        return None

    def _extract_category_from_class(self, article_class: str) -> str:
        """Extract category from article class attribute"""
        for cat_key, cat_name in self.category_mapping.items():
            if f'categorie-{cat_key}' in article_class:
                return cat_name
        return 'General'

    def generate_token(self, source_url: str, timestamp: int) -> str:
        """Generate token for video source authentication"""
        raw_token = f"{source_url}{timestamp}{self.config.SECRET_KEY}"
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def get_video_source(self, post_id: str) -> Optional[str]:
        """Get the first available video source for a channel with caching"""
        if self.shutdown_flag:
            return None
            
        # Check cache first
        if post_id in self.video_cache:
            cached_time, cached_url = self.video_cache[post_id]
            if time.time() - cached_time < self.config.CACHE_EXPIRY:
                return cached_url
        
        ajax_url = f'{self.config.BASE_URL}/wp-admin/admin-ajax.php'
        ajax_headers = {
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            data = {
                'action': 'get_video_source',
                'tab': 'tab1',
                'post_id': post_id,
            }
            response = self.session.post(
                ajax_url, 
                headers=ajax_headers, 
                data=data, 
                timeout=self.config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            json_response = response.json()
            
            if json_response.get('success'):
                raw_source_url = json_response.get('data')
                if raw_source_url:
                    if 'token=' in raw_source_url:
                        final_url = raw_source_url
                    else:
                        final_url = self.get_stream_from_channel_page(post_id)
                        if not final_url:
                            timestamp = int(time.time())
                            token = self.generate_token(raw_source_url, timestamp)
                            embed_url = (
                                f"https://ivanturbinca.com/embed-video2.php?"
                                f"source={raw_source_url}&token={token}&timestamp={timestamp}"
                            )
                            final_url = self.get_final_video_url(embed_url)
                    
                    if final_url:
                        self.video_cache[post_id] = (time.time(), final_url)
                        return final_url
        except Exception as e:
            logger.debug(f"Error getting video source for channel {post_id}: {e}")
        
        return None

    def get_stream_from_channel_page(self, post_id: str) -> Optional[str]:
        """Try to get stream URL directly from the channel page"""
        if self.shutdown_flag:
            return None
            
        try:
            channel_url = f"{self.config.BASE_URL}/?p={post_id}"
            response = self.session.get(channel_url, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', response.text)
            if iframe_match:
                iframe_url = iframe_match.group(1)
                if 'token=' in iframe_url:
                    return iframe_url
            
            video_match = re.search(r'<video[^>]+src="([^"]+)"', response.text)
            if video_match:
                return video_match.group(1)
                
            script_match = re.search(r'src:\s*["\']([^"\']+)["\']', response.text)
            if script_match and ('.m3u8' in script_match.group(1) or '.mp4' in script_match.group(1)):
                return script_match.group(1)
                
        except Exception as e:
            logger.debug(f"Error getting stream from channel page {post_id}: {e}")
        
        return None

    def get_final_video_url(self, embed_url: str) -> Optional[str]:
        """Extract final video URL from embed page"""
        if self.shutdown_flag:
            return None
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Referer': self.config.BASE_URL,
                'Accept': '*/*',
            }
            
            response = self.session.get(embed_url, headers=headers, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            patterns = [
                r'<source src="([^"]+)"',
                r'file:\s*"([^"]+)"',
                r'videoUrl:\s*"([^"]+)"',
                r'src:\s*"([^"]+)"',
                r'var\s+url\s*=\s*"([^"]+)"',
                r'playlist:\s*\[\{\s*file:\s*"([^"]+)"'
            ]
            
            for pattern in patterns:
                video_source_match = re.search(pattern, response.text, re.IGNORECASE)
                if video_source_match:
                    url = video_source_match.group(1)
                    if url.startswith('//'):
                        url = 'https:' + url
                    return url
                    
            iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', response.text)
            if iframe_match:
                iframe_url = iframe_match.group(1)
                if iframe_url.startswith('//'):
                    iframe_url = 'https:' + iframe_url
                return self.get_final_video_url(iframe_url)
                
        except Exception as e:
            logger.debug(f"Error getting final video URL from {embed_url}: {e}")
        return None

    def generate_m3u(self, channels: List[Channel]) -> str:
        """Generate M3U playlist content with stream URLs and EPG support"""
        m3u_content = "#EXTM3U\n"
        m3u_content += f'#EXT-X-SESSION-DATA:DATA-ID="com.apple.quicktime.player.name",VALUE="RDS Live M3U Generator"\n'
        m3u_content += f'#EXT-X-SESSION-DATA:DATA-ID="com.apple.quicktime.player.version",VALUE="1.0"\n'
        
        if self.config.EPG_URL:
            m3u_content += f'#EXT-X-SESSION-DATA:DATA-ID="com.apple.quicktime.player.epg",VALUE="{self.config.EPG_URL}"\n'
            m3u_content += f'#X-TVG-URL="{self.config.EPG_URL}"\n'
        
        m3u_content += f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        m3u_content += f"# Total channels: {len(channels)}\n\n"
        
        working_count = 0
        failed_count = 0
        
        for i, channel in enumerate(channels):
            if self.shutdown_flag:
                logger.info(f"Shutdown requested, stopping at channel {i+1}/{len(channels)}")
                break
                
            try:
                video_url = self.get_video_source(channel.id)
                if video_url:
                    m3u_content += self._format_channel_entry(channel, video_url)
                    working_count += 1
                    channel.stream_url = video_url
                else:
                    m3u_content += self._format_channel_entry(channel, None)
                    failed_count += 1
            except Exception as e:
                logger.warning(f"Error processing channel {channel.id}: {e}")
                m3u_content += self._format_channel_entry(channel, None)
                failed_count += 1
        
        self.stats.working_streams = working_count
        self.stats.failed_streams = failed_count
        return m3u_content

    def _format_channel_entry(self, channel: Channel, url: Optional[str]) -> str:
        """Format a single channel entry in M3U with EPG tags"""
        entry = f'#EXTINF:-1'
        
        if channel.tvg_id:
            entry += f' tvg-id="{channel.tvg_id}"'
        if channel.tvg_name:
            entry += f' tvg-name="{channel.tvg_name}"'
        if channel.tvg_logo:
            entry += f' tvg-logo="{channel.tvg_logo}"'
        if channel.tvg_shift:
            entry += f' tvg-shift="{channel.tvg_shift}"'
        if channel.tvg_chno:
            entry += f' tvg-chno="{channel.tvg_chno}"'
        
        entry += f' group-title="{channel.category}",{channel.title}\n'
        
        if url:
            entry += f"{url}\n\n"
        else:
            entry += f"# Stream not available for {channel.title}\n\n"
        return entry

    def generate_epg(self, channels: List[Channel]) -> str:
        """Generate EPG (XMLTV) content"""
        tv = ET.Element("tv")
        tv.set("source-info-name", "RDS Live M3U Generator")
        tv.set("generator-info-name", "RDS Live M3U Generator")
        tv.set("generator-info-url", "https://huggingface.co/spaces/YOUR_USERNAME/rds-live-m3u-generator")
        
        for channel in channels:
            channel_elem = ET.SubElement(tv, "channel")
            channel_elem.set("id", channel.tvg_id or channel.id)
            
            display_name = ET.SubElement(channel_elem, "display-name")
            display_name.text = channel.title
            display_name.set("lang", "ro")
            
            if channel.tvg_logo:
                icon = ET.SubElement(channel_elem, "icon")
                icon.set("src", channel.tvg_logo)
        
        now = datetime.now()
        for channel in channels:
            for i in range(6):
                start_time = now + timedelta(hours=i*4)
                end_time = start_time + timedelta(hours=4)
                
                program_elem = ET.SubElement(tv, "programme")
                program_elem.set("start", start_time.strftime("%Y%m%d%H%M%S +0200"))
                program_elem.set("stop", end_time.strftime("%Y%m%d%H%M%S +0200"))
                program_elem.set("channel", channel.tvg_id or channel.id)
                
                title_elem = ET.SubElement(program_elem, "title")
                title_elem.text = f"Program {i+1} - {channel.title}"
                title_elem.set("lang", "ro")
                
                desc_elem = ET.SubElement(program_elem, "desc")
                desc_elem.text = f"Placeholder program {i+1} for {channel.title}"
                desc_elem.set("lang", "ro")
                
                cat_elem = ET.SubElement(program_elem, "category")
                cat_elem.text = channel.category
                cat_elem.set("lang", "ro")
        
        rough_string = ET.tostring(tv, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    def update_playlist(self) -> bool:
        """Update the M3U playlist with stream URLs"""
        if self.update_in_progress:
            logger.warning("Update already in progress")
            return False
            
        self.update_in_progress = True
        start_time = time.time()
        
        try:
            logger.info("Starting playlist update...")
            channels = self.extract_all_channels()
            
            if channels:
                self.last_channels = channels
                self.last_update = datetime.now()
                self.stats.total_updates += 1
                self.stats.last_update = self.last_update.isoformat()
                self.stats.total_channels = len(channels)
                
                m3u_content = self.generate_m3u(channels)
                self.m3u_content = m3u_content
                with open('/app/rdslive_streams.m3u', 'w', encoding='utf-8') as f:
                    f.write(m3u_content)
                
                epg_content = self.generate_epg(channels)
                self.epg_content = epg_content
                with open('/app/rdslive_epg.xml', 'w', encoding='utf-8') as f:
                    f.write(epg_content)
                
                self.stats.epg_programs = len(channels) * 6
                
                duration = time.time() - start_time
                self.stats.last_update_duration = duration
                logger.info(f"Playlist updated successfully. {len(channels)} channels found in {duration:.2f}s.")
                logger.info(f"Working streams: {self.stats.working_streams}, Failed: {self.stats.failed_streams}")
                logger.info(f"EPG programs: {self.stats.epg_programs}")
                return True
            else:
                logger.error("No channels found during update")
                return False
                
        except Exception as e:
            logger.error(f"Error during playlist update: {e}", exc_info=True)
            return False
        finally:
            self.update_in_progress = False

    def get_channel_by_id(self, channel_id: str) -> Optional[Channel]:
        """Get a channel by its ID"""
        for channel in self.last_channels:
            if channel.id == channel_id:
                return channel
        return None
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_flag = True

# Initialize configuration
config = Config()
# Initialize the generator
generator = RDSLiveM3UGenerator(config)
# Flask app
app = Flask(__name__)

# Web interface HTML template
WEB_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>RDS Live M3U Generator with EPG</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #e3f2fd; padding: 15px; border-radius: 5px; text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; color: #1976d2; }
        .stat-label { font-size: 14px; color: #666; }
        .buttons { text-align: center; margin: 20px 0; }
        .btn { display: inline-block; margin: 5px; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; }
        .btn:hover { background: #1565c0; }
        .btn.secondary { background: #757575; }
        .btn.secondary:hover { background: #616161; }
        .status { margin: 20px 0; padding: 10px; border-radius: 5px; }
        .status.updating { background: #fff3e0; border: 1px solid #ff9800; }
        .status.success { background: #e8f5e8; border: 1px solid #4caf50; }
        .status.error { background: #ffebee; border: 1px solid #f44336; }
        .log { background: #f8f9fa; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .channels-list { margin-top: 20px; }
        .channel-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; align-items: center; }
        .channel-logo { width: 50px; height: 50px; object-fit: contain; margin-right: 15px; }
        .channel-info { flex-grow: 1; }
        .channel-title { font-weight: bold; }
        .channel-category { color: #666; font-size: 0.9em; }
        .filter-container { margin: 20px 0; }
        .filter-input { padding: 8px; width: 100%; border: 1px solid #ddd; border-radius: 4px; }
        .tab-container { margin: 20px 0; }
        .tab { display: inline-block; padding: 10px 20px; background: #e0e0e0; cursor: pointer; }
        .tab.active { background: #1976d2; color: white; }
        .tab-content { display: none; padding: 20px; border: 1px solid #ddd; border-top: none; }
        .tab-content.active { display: block; }
        .highlight { background-color: #fffde7; padding: 10px; border-radius: 5px; margin: 10px 0; }
        .url-box { background: #f5f5f5; padding: 10px; border-radius: 5px; font-family: monospace; word-break: break-all; margin: 10px 0; }
        .copy-btn { background: #4caf50; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; margin-left: 10px; }
        .copy-btn:hover { background: #45a049; }
        .warning { background-color: #fff3e0; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ff9800; }
        .working { color: #4caf50; font-weight: bold; }
        .failed { color: #f44336; font-weight: bold; }
    </style>
    <script>
        let allChannels = [];
        
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-updates').textContent = data.total_updates;
                    document.getElementById('total-channels').textContent = data.total_channels;
                    document.getElementById('working-streams').textContent = data.working_streams;
                    document.getElementById('failed-streams').textContent = data.failed_streams;
                    document.getElementById('epg-programs').textContent = data.epg_programs;
                    document.getElementById('last-update').textContent = data.last_update || 'Never';
                    document.getElementById('update-duration').textContent = 
                        data.last_update_duration ? data.last_update_duration.toFixed(2) + 's' : 'N/A';
                });
        }
        
        function loadChannels() {
            fetch('/api/channels')
                .then(response => response.json())
                .then(data => {
                    allChannels = data.channels;
                    renderChannels(allChannels);
                });
        }
        
        function renderChannels(channels) {
            const container = document.getElementById('channels-container');
            container.innerHTML = '';
            
            channels.forEach(channel => {
                const item = document.createElement('div');
                item.className = 'channel-item';
                
                const logo = channel.poster ? 
                    `<img src="${channel.poster}" alt="${channel.title}" class="channel-logo" onerror="this.style.display='none'">` :
                    '<div class="channel-logo" style="background:#eee;"></div>';
                
                const status = channel.stream_url ? 
                    `<span class="working">✓ Working</span>` : 
                    `<span class="failed">✗ Failed</span>`;
                
                const playBtn = channel.stream_url ? 
                    `<button class="btn" onclick="playChannel('${channel.id}')">Play</button>` : '';
                
                item.innerHTML = `
                    ${logo}
                    <div class="channel-info">
                        <div class="channel-title">${channel.title}</div>
                        <div class="channel-category">${channel.category} ${status}</div>
                    </div>
                    ${playBtn}
                `;
                
                container.appendChild(item);
            });
        }
        
        function filterChannels() {
            const searchTerm = document.getElementById('filter-input').value.toLowerCase();
            const filtered = allChannels.filter(channel => 
                channel.title.toLowerCase().includes(searchTerm) || 
                channel.category.toLowerCase().includes(searchTerm)
            );
            renderChannels(filtered);
        }
        
        function updatePlaylist() {
            const button = event.target;
            const originalText = button.textContent;
            button.textContent = 'Updating...';
            button.disabled = true;
            
            showStatus('Update in progress...', 'updating');
            
            fetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showStatus('Update completed successfully!', 'success');
                    updateStats();
                    loadChannels();
                } else {
                    showStatus('Update failed: ' + data.message, 'error');
                }
            })
            .catch(error => {
                showStatus('Update failed: ' + error.message, 'error');
            })
            .finally(() => {
                button.textContent = originalText;
                button.disabled = false;
            });
        }
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.textContent = message;
            statusDiv.className = 'status ' + type;
            
            if (type !== 'updating') {
                setTimeout(() => {
                    statusDiv.textContent = '';
                    statusDiv.className = 'status';
                }, 5000);
            }
        }
        
        function openTab(tabName) {
            const tabContents = document.getElementsByClassName('tab-content');
            for (let i = 0; i < tabContents.length; i++) {
                tabContents[i].classList.remove('active');
            }
            
            const tabs = document.getElementsByClassName('tab');
            for (let i = 0; i < tabs.length; i++) {
                tabs[i].classList.remove('active');
            }
            
            document.getElementById(tabName).classList.add('active');
            event.currentTarget.classList.add('active');
        }
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                alert('URL copied to clipboard!');
            }).catch(err => {
                console.error('Failed to copy: ', err);
            });
        }
        
        function playChannel(channelId) {
            const channel = allChannels.find(c => c.id === channelId);
            if (channel && channel.stream_url) {
                window.open(channel.stream_url, '_blank');
            }
        }
        
        setInterval(updateStats, 30000);
        
        window.onload = function() {
            updateStats();
            loadChannels();
        };
    </script>
</head>
<body>
    <div class="container">
        <h1>🚀 RDS Live M3U Generator with EPG</h1>
        
        <div class="warning">
            <strong>⚠️ Optimized for Hugging Face Spaces</strong><br>
            This service generates both M3U playlists and EPG (Electronic Program Guide) data.
        </div>
        
        <div class="highlight">
            <strong>📺 Direct IPTV Streaming</strong><br>
            Use these URLs directly in your IPTV player without downloading the playlist:
        </div>
        
        <div class="url-box">
            <strong>M3U Playlist URL:</strong> http://{{ request.host }}/m3u
            <button class="copy-btn" onclick="copyToClipboard('http://{{ request.host }}/m3u')">Copy</button>
        </div>
        
        <div class="url-box">
            <strong>EPG URL:</strong> http://{{ request.host }}/epg
            <button class="copy-btn" onclick="copyToClipboard('http://{{ request.host }}/epg')">Copy</button>
        </div>
        
        <div id="status" class="status"></div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="total-updates">{{ stats.total_updates }}</div>
                <div class="stat-label">Total Updates</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="total-channels">{{ stats.total_channels }}</div>
                <div class="stat-label">Total Channels</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="working-streams">{{ stats.working_streams }}</div>
                <div class="stat-label">Working Streams</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="failed-streams">{{ stats.failed_streams }}</div>
                <div class="stat-label">Failed Streams</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="epg-programs">{{ stats.epg_programs }}</div>
                <div class="stat-label">EPG Programs</div>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-label">Last Update</div>
            <div id="last-update">{{ stats.last_update or 'Never' }}</div>
            <div class="stat-label">Duration</div>
            <div id="update-duration">{{ stats.last_update_duration or 'N/A' }}</div>
        </div>
        
        <div class="buttons">
            <button class="btn" onclick="updatePlaylist()">Update Playlist</button>
            <a href="/playlist" class="btn">Download M3U</a>
            <a href="/epg-download" class="btn secondary">Download EPG</a>
        </div>
        
        <div class="tab-container">
            <button class="tab active" onclick="openTab('channels-tab')">Channels</button>
            <button class="tab" onclick="openTab('api-tab')">API</button>
        </div>
        
        <div id="channels-tab" class="tab-content active">
            <div class="filter-container">
                <input type="text" id="filter-input" class="filter-input" placeholder="Filter channels..." onkeyup="filterChannels()">
            </div>
            
            <div class="channels-list">
                <h3>Channels ({{ stats.total_channels }})</h3>
                <div id="channels-container"></div>
            </div>
        </div>
        
        <div id="api-tab" class="tab-content">
            <h3>API Endpoints</h3>
            <div class="log">
GET  /m3u              - Stream M3U playlist for IPTV players
GET  /epg              - Stream EPG (XMLTV) data
GET  /playlist          - Download M3U with stream URLs
GET  /epg.xml          - Download EPG (XMLTV) file
GET  /api/stats         - Get service statistics
POST /api/update        - Trigger manual update
GET  /api/channels      - Get channels as JSON
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Web interface"""
    return render_template_string(WEB_TEMPLATE, stats=asdict(generator.stats), request=request)

@app.route('/m3u')
def stream_m3u():
    """Stream M3U playlist for direct IPTV playback"""
    if not generator.m3u_content or not generator.last_channels:
        generator.update_playlist()
    
    return Response(
        generator.m3u_content,
        mimetype='audio/x-mpegurl',
        headers={
            'Content-Disposition': 'inline; filename="rdslive_streams.m3u"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

@app.route('/epg')
@app.route('/epg.xml')
def stream_epg():
    """Stream EPG (XMLTV) data for IPTV players"""
    if not generator.epg_content or not generator.last_channels:
        generator.update_playlist()
    
    return Response(
        generator.epg_content,
        mimetype='application/xml',
        headers={
            'Content-Disposition': 'inline; filename="rdslive_epg.xml"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

@app.route('/playlist')
def download_playlist():
    """Download M3U playlist with stream URLs"""
    if not os.path.exists('/app/rdslive_streams.m3u'):
        generator.update_playlist()
    
    return send_file('/app/rdslive_streams.m3u',
                    mimetype='audio/x-mpegurl', 
                    as_attachment=True,
                    download_name='rdslive_streams.m3u')

@app.route('/epg-download')
def download_epg():
    """Download EPG (XMLTV) file"""
    if not os.path.exists('/app/rdslive_epg.xml'):
        generator.update_playlist()
    
    return send_file('/app/rdslive_epg.xml',
                    mimetype='application/xml', 
                    as_attachment=True,
                    download_name='rdslive_epg.xml')

@app.route('/api/stats')
def api_stats():
    """Get service statistics"""
    return jsonify(asdict(generator.stats))

@app.route('/api/channels')
def api_channels():
    """Get channels as JSON"""
    return jsonify({
        'channels': [asdict(channel) for channel in generator.last_channels],
        'last_update': generator.last_update.isoformat() if generator.last_update else None,
        'total': len(generator.last_channels)
    })

@app.route('/api/update', methods=['POST'])
def api_update():
    """Trigger manual update"""
    try:
        success = generator.update_playlist()
        
        return jsonify({
            'success': success,
            'message': 'Update completed successfully' if success else 'Update failed',
            'stats': asdict(generator.stats)
        })
    except Exception as e:
        logger.error(f"API update error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

def auto_update_scheduler():
    """Background thread for automatic updates"""
    while not generator.shutdown_flag:
        try:
            time.sleep(config.UPDATE_INTERVAL)
            if generator.shutdown_flag:
                break
            logger.info("Running scheduled update...")
            generator.update_playlist()
        except Exception as e:
            logger.error(f"Error in auto-update scheduler: {e}", exc_info=True)

def start_background_updater():
    """Start the background update thread"""
    thread = threading.Thread(target=auto_update_scheduler, daemon=True)
    thread.start()
    logger.info(f"Background updater started (every {config.UPDATE_INTERVAL} seconds)")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    generator.shutdown_flag = True
    time.sleep(2)
    sys.exit(0)

if __name__ == '__main__':
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create necessary directories
    os.makedirs('/app/logs', exist_ok=True)
    
    # Initial playlist generation
    logger.info("Generating initial playlist...")
    generator.update_playlist()
    
    # Start background updater
    start_background_updater()
    
    # Start Flask app
    logger.info(f"Starting Flask app on port {config.PORT}")
    try:
        app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        generator.shutdown_flag = True
        sys.exit(0)