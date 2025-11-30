# YouTube Comment Extractor 📺💬

A robust desktop application built with Python and CustomTkinter for extracting high-quality data from YouTube videos. Designed for researchers, data analysts, and creators who need clean, organized comment data without the noise.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## 🚀 Key Features

*   **Batch Processing**: Queue up multiple video URLs (one per line) and process them sequentially.
*   **Clean Data**: Built-in **Spam/Bot Filter** automatically removes comments containing common spam keywords (e.g., "crypto", "whatsapp", "invest") and phone number patterns.
*   **Smart Sorting**: Fetches comments using YouTube's "Relevance" metric and sorts the final output by **Like Count (Descending)** to prioritize high-signal discussions.
*   **Dual Export**: Generates two separate CSV files for each video to avoid data redundancy:
    *   `_metadata.csv`: Video Title, Views, Likes, Comment Count, Published Date.
    *   `_comments.csv`: Comment Text, Author, Date, Likes, Reply Count.
*   **Modern UI**: Sleek, dark-themed interface built with `CustomTkinter` featuring real-time progress logs.
*   **Persistent Settings**: Automatically saves your API Key locally so you don't have to re-enter it.
*   **Rate Limiting**: Includes random delays between batch requests to respect YouTube API limits.

## 🛠️ Installation

### Prerequisites
*   Python 3.8 or higher
*   A Google Cloud Project with **YouTube Data API v3** enabled.

### Setup

1.  **Clone the repository**
    ```bash
    git clone https://github.com/vijaykumarpeta/yt-comments-extractor.git
    cd yt-comments-extractor
    ```

2.  **Create a Virtual Environment (Recommended)**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## 📖 Usage

1.  **Get your YouTube API Key**
    *   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Create a project and enable the **YouTube Data API v3**.
    *   Create Credentials (API Key).

2.  **Run the Application**
    ```bash
    python main.py
    ```

3.  **Using the App**
    *   Paste your **API Key** into the designated field.
    *   Paste **YouTube Video URLs** into the text box (one URL per line).
    *   (Optional) Uncheck "Filter Spam/Bots" if you want raw data.
    *   Click **Fetch All**.
    *   Once processing is complete, click **Export CSVs** to save your data.

## 📦 Building the Executable (.exe)

You can convert this Python script into a standalone Windows executable that runs on any machine without Python installed.

1.  **Install PyInstaller**
    ```bash
    pip install pyinstaller
    ```

2.  **Build the App**
    ```bash
    pyinstaller --noconfirm --onefile --windowed --name "YouTubeCommentExtractor" --collect-all customtkinter main.py
    ```

3.  **Locate the Exe**
    The finished `YouTubeCommentExtractor.exe` will be in the `dist/` folder.

## 📂 Project Structure

```
yt-comments-extractor/
├── main.py             # GUI entry point and application logic
├── extractor.py        # YouTube API interaction and data processing logic
├── requirements.txt    # Python dependencies
├── settings.json       # Local storage for API Key (auto-generated)
└── README.md           # Documentation
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

