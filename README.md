# RDS Live M3U Generator with EPG Support

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.3.3-green.svg)
![Podman](https://img.shields.io/badge/podman-4.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A Flask-based service that automatically generates M3U playlists with EPG (Electronic Program Guide) support for RDS Live TV channels.

## Features

- 📺 **Live TV Channel Extraction**: Automatically extracts TV channel information from RDS Live website
- 🔄 **Auto-Update**: Automatically refreshes playlists and EPG data
- 🎬 **Stream URL Extraction**: Extracts actual stream URLs for each channel
- 📋 **EPG Support**: Generates Electronic Program Guide data in XMLTV format
- 🌐 **Web Interface**: User-friendly dashboard with statistics and controls
- 🐳 **REST API**: Programmatic access to playlists and data
- 📦 **Container Ready**: Includes Podman support for easy deployment

## Quick Start

### Using Podman (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rds-live-m3u-generator.git
cd rds-live-m3u-generator
