import gradio as gr
import requests
from bs4 import BeautifulSoup

def generate_m3u():
    try:
        url = "https://www.rds.ro/rds-live"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        streams = []
        for link in soup.select('a[href*="m3u8"]'):
            stream_url = link['href']
            if not stream_url.startswith('http'):
                stream_url = "https://www.rds.ro" + stream_url
            streams.append(f"#EXTINF:-1,RDS Live\n{stream_url}")
        
        if not streams:
            return "No streams found. Check site structure."
        
        return "#EXTM3U\n" + "\n".join(streams)
    except Exception as e:
        return f"Error: {str(e)}"

def generate_and_download():
    m3u_content = generate_m3u()
    return m3u_content, "rds_live.m3u"

with gr.Blocks() as demo:
    gr.Markdown("# RDS Live M3U Generator")
    generate_btn = gr.Button("Generate M3U Playlist")
    output_text = gr.Textbox(label="M3U Content", lines=10)
    download_btn = gr.DownloadButton("Download M3U", visible=False)

    generate_btn.click(
        fn=generate_and_download,
        outputs=[output_text, download_btn]
    )

if __name__ == "__main__":
    demo.launch()
