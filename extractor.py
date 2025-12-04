import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
import time

class YouTubeCommentExtractor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)

    def get_video_id(self, url):
        """Extracts the video ID from a YouTube URL."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def fetch_video_details(self, video_id):
        """Fetches video metadata."""
        try:
            request = self.youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            )
            response = request.execute()
            
            if not response['items']:
                return None

            item = response['items'][0]
            snippet = item['snippet']
            stats = item['statistics']

            return {
                'Video Title': snippet['title'],
                'Video Date': snippet['publishedAt'],
                'Video Views': stats.get('viewCount', 0),
                'Video Likes': stats.get('likeCount', 0),
                'Video Comment Count': stats.get('commentCount', 0)
            }
        except Exception as e:
            print(f"Error fetching video details: {e}")
            return None

    def is_spam(self, text):
        """Checks if the comment text contains common spam keywords."""
        spam_keywords = [
            'whatsapp', 'telegram', 'invest', 'crypto', 'forex', 'bitcoin', 'btc', 
            'trading', 'fx', 'binance', 'coinbase', 'usdt', 'contact me', 
            'message me', 'dm me'
        ]
        
        text_lower = text.lower()
        
        # Check for keywords
        for keyword in spam_keywords:
            if keyword in text_lower:
                return True
                
        # Check for phone number patterns (simplified)
        # Matches things like +1 234..., +44..., numbers with brackets
        if re.search(r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', text):
            return True
            
        return False

    def process_video(self, video_url, max_results=None, progress_callback=None, filter_spam=False):
        """
        Fetches metadata and comments for a video.
        Returns a tuple: (metadata_dict, comments_list)
        """
        video_id = self.get_video_id(video_url)
        if not video_id:
            raise ValueError(f"Invalid YouTube URL: {video_url}")

        # 1. Fetch Video Metadata
        video_details = self.fetch_video_details(video_id)
        if not video_details:
            raise ValueError(f"Could not fetch details for video {video_id}")
            
        # Add Video ID to metadata
        video_details['Video ID'] = video_id

        # 2. Fetch Comments
        comments = []
        
        try:
            request = self.youtube.commentThreads().list(
                part="snippet", # Removed 'replies' to fetch only top-level comments
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                order="relevance" # Fetch top comments first (like YouTube UI)
            )

            while request:
                if max_results and len(comments) >= max_results:
                    break

                response = request.execute()

                for item in response['items']:
                    # Top level comment
                    top_comment = item['snippet']['topLevelComment']['snippet']
                    text_display = top_comment['textDisplay']
                    
                    # Spam Filter
                    if filter_spam and self.is_spam(text_display):
                        continue

                    # Comment data (Linked by Video ID)
                    comment_data = {
                        'Video ID': video_id,
                        'Comment Text': text_display,
                        'Comment Date': top_comment['publishedAt'],
                        'Comment Likes': top_comment['likeCount'],
                        'Replies': item['snippet']['totalReplyCount'],
                        'Type': 'Comment'
                    }
                    comments.append(comment_data)
                    
                    if max_results and len(comments) >= max_results:
                        break
                
                if progress_callback:
                    progress_callback(len(comments))

                if 'nextPageToken' in response:
                    # Small delay between pages to be nice to the API
                    time.sleep(0.5)
                    request = self.youtube.commentThreads().list(
                        part="snippet", # Removed 'replies'
                        videoId=video_id,
                        maxResults=100,
                        textFormat="plainText",
                        pageToken=response['nextPageToken'],
                        order="relevance"
                    )
                else:
                    break
                    
        except HttpError as e:
            # If comments are disabled, we might still want to return metadata
            if e.resp.status == 403: # Comments disabled
                print(f"Comments disabled for video {video_id}")
            else:
                raise Exception(f"An HTTP error occurred: {e.resp.status} {e.content}")
        except Exception as e:
            raise Exception(f"An error occurred: {str(e)}")

        # Sort comments by Likes (Descending) to improve signal-to-noise ratio
        comments.sort(key=lambda x: x['Comment Likes'], reverse=True)

        return video_details, comments

    def save_to_csv(self, metadata_list, comments_list, base_filename):
        # Save Metadata
        if metadata_list:
            df_meta = pd.DataFrame(metadata_list)
            meta_filename = f"{base_filename}_metadata.csv"
            df_meta.to_csv(meta_filename, index=False)
        
        # Save Comments
        if comments_list:
            df_comments = pd.DataFrame(comments_list)
            comments_filename = f"{base_filename}_comments.csv"
            df_comments.to_csv(comments_filename, index=False)
            
        return base_filename


