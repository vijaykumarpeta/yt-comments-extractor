import customtkinter as ctk
import threading
from tkinter import filedialog, messagebox
import json
import os
import time
import random
from extractor import YouTubeCommentExtractor

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

SETTINGS_FILE = "settings.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Comment Extractor")
        self.geometry("900x700")
        
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) # Preview frame expands

        self.extractor = None
        self.all_metadata = []
        self.all_comments = []

        # --- Input Section ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        self.input_frame.grid_columnconfigure(1, weight=1)

        # API Key
        self.api_key_label = ctk.CTkLabel(self.input_frame, text="YouTube API Key:")
        self.api_key_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.api_key_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Enter your Google API Key")
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # --- URL Section ---
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.url_frame.grid_columnconfigure(1, weight=1)

        self.url_label = ctk.CTkLabel(self.url_frame, text="Video URLs (one per line):")
        self.url_label.grid(row=0, column=0, padx=10, pady=10, sticky="n")

        self.url_entry = ctk.CTkTextbox(self.url_frame, height=100)
        self.url_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.url_entry.insert("1.0", "https://www.youtube.com/watch?v=...")

        self.fetch_button = ctk.CTkButton(self.url_frame, text="Fetch All", command=self.start_fetching)
        self.fetch_button.grid(row=0, column=2, padx=10, pady=10, sticky="n")
        
        self.spam_filter_var = ctk.BooleanVar(value=True)
        self.spam_filter_checkbox = ctk.CTkCheckBox(self.url_frame, text="Filter Spam/Bots", variable=self.spam_filter_var)
        self.spam_filter_checkbox.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="w")

        # --- Progress Section ---
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.progress_frame, text="Ready", text_color="gray")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.progress_bar.set(0)

        # --- Comments Preview Section ---
        self.preview_frame = ctk.CTkScrollableFrame(self, label_text="Log / Preview")
        self.preview_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")

        # --- Export Section ---
        self.export_button = ctk.CTkButton(self, text="Export CSVs", command=self.export_csv, state="disabled")
        self.export_button.grid(row=4, column=0, padx=20, pady=20, sticky="e")

        # Load Settings
        self.load_settings()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    api_key = settings.get('api_key', '')
                    if api_key:
                        self.api_key_entry.insert(0, api_key)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        api_key = self.api_key_entry.get().strip()
        settings = {'api_key': api_key}
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def start_fetching(self):
        api_key = self.api_key_entry.get().strip()
        raw_urls = self.url_entry.get("1.0", "end").strip().split('\n')
        urls = [u.strip() for u in raw_urls if u.strip() and "youtube" in u or "youtu.be" in u]
        filter_spam = self.spam_filter_var.get()

        if not api_key:
            messagebox.showerror("Error", "Please enter an API Key.")
            return
        if not urls:
            messagebox.showerror("Error", "Please enter at least one valid YouTube Video URL.")
            return

        # Save settings on successful start
        self.save_settings()

        self.fetch_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(text="Initializing...", text_color="white")
        
        # Clear previous preview
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
            
        self.all_metadata = []
        self.all_comments = []

        self.extractor = YouTubeCommentExtractor(api_key)
        
        # Run in a separate thread
        threading.Thread(target=self.fetch_thread, args=(urls, filter_spam), daemon=True).start()

    def fetch_thread(self, urls, filter_spam):
        total_videos = len(urls)
        
        try:
            for i, url in enumerate(urls):
                self.after(0, lambda u=url: self.status_label.configure(text=f"Processing {i+1}/{total_videos}: {u}"))
                self.after(0, lambda msg=f"Processing: {url}": self.log_message(msg))
                
                try:
                    metadata, comments = self.extractor.process_video(
                        url, 
                        max_results=None, 
                        progress_callback=None, # simplified for batch
                        filter_spam=filter_spam
                    )
                    
                    self.all_metadata.append(metadata)
                    self.all_comments.extend(comments)
                    
                    self.after(0, lambda msg=f"  - Fetched {len(comments)} comments.": self.log_message(msg))
                    
                except Exception as e:
                    self.after(0, lambda msg=f"  - Error: {str(e)}": self.log_message(msg, color="red"))
                
                # Update progress bar
                self.after(0, lambda val=(i+1)/total_videos: self.progress_bar.set(val))
                
                # Add delay between videos to avoid rate limits (2-5 seconds)
                if i < total_videos - 1:
                    delay = random.uniform(2.0, 5.0)
                    self.after(0, lambda msg=f"  - Waiting {delay:.1f}s...": self.log_message(msg, color="gray"))
                    time.sleep(delay)

            self.after(0, lambda: self.status_label.configure(text=f"Completed. Fetched data for {len(self.all_metadata)} videos.", text_color="green"))
            self.after(0, lambda: self.export_button.configure(state="normal"))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_label.configure(text="Error occurred.", text_color="red"))
        finally:
            self.after(0, lambda: self.fetch_button.configure(state="normal"))

    def log_message(self, message, color="white"):
        label = ctk.CTkLabel(self.preview_frame, text=message, text_color=color, anchor="w", justify="left")
        label.pack(fill="x", padx=5, pady=2)

    def export_csv(self):
        if not self.all_metadata and not self.all_comments:
            return
            
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if filename:
            # Remove extension to get base name
            base_filename = os.path.splitext(filename)[0]
            try:
                self.extractor.save_to_csv(self.all_metadata, self.all_comments, base_filename)
                messagebox.showinfo("Success", f"Saved files:\n{base_filename}_metadata.csv\n{base_filename}_comments.csv")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
