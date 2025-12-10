"""
YouTube Comment Extractor Module.

Provides functionality to extract comments and metadata from YouTube videos
using the YouTube Data API v3.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from core.constants import (
    YOUTUBE_API_SERVICE_NAME,
    YOUTUBE_API_VERSION,
    YOUTUBE_COMMENTS_PER_PAGE,
    API_DELAY_BETWEEN_PAGES,
    SortOption,
)
from core.validators import URLValidator, WordsFilterValidator
from spam_filter import SpamDetector, SpamResult

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class VideoMetadata:
    """Video metadata from YouTube API."""
    video_id: str
    title: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    channel_id: str
    url: str
    spam_filtered: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "Video ID": self.video_id,
            "Video Title": self.title,
            "Video Date": self.published_at,
            "Video Views": self.view_count,
            "Video Likes": self.like_count,
            "Video Comment Count": self.comment_count,
            "Video URL": self.url,
            "Spam Filtered": self.spam_filtered,
        }


@dataclass
class Comment:
    """Comment data from YouTube API."""
    video_id: str
    author_name: str
    author_channel_id: str
    text: str
    published_at: str
    like_count: int
    reply_count: int
    is_creator: bool = False

    def to_dict(self, include_is_creator: bool = True) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        data = {
            "Video ID": self.video_id,
            "Author Name": self.author_name,
            "Comment Text": self.text,
            "Comment Date": self.published_at,
            "Comment Likes": self.like_count,
            "Replies": self.reply_count,
        }
        if include_is_creator:
            data["Is Creator"] = self.is_creator
        return data


@dataclass
class SpamComment:
    """Spam comment with detection details."""
    video_id: str
    author_name: str
    text: str
    published_at: str
    like_count: int
    spam_score: float
    spam_reason: str
    spam_category: str
    had_obfuscation: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "Video ID": self.video_id,
            "Author Name": self.author_name,
            "Comment Text": self.text,
            "Comment Date": self.published_at,
            "Comment Likes": self.like_count,
            "Spam Score": self.spam_score,
            "Spam Reason": self.spam_reason,
            "Spam Category": self.spam_category,
            "Had Obfuscation": self.had_obfuscation,
        }


@dataclass
class ExtractionResult:
    """Result of video comment extraction."""
    metadata: VideoMetadata
    comments: List[Comment]
    spam_comments: List[SpamComment]


# =============================================================================
# EXCEPTIONS
# =============================================================================

class YouTubeAPIError(Exception):
    """Base exception for YouTube API errors."""
    pass


class VideoNotFoundError(YouTubeAPIError):
    """Video was not found."""
    pass


class CommentsDisabledError(YouTubeAPIError):
    """Comments are disabled for this video."""
    pass


class QuotaExceededError(YouTubeAPIError):
    """API quota has been exceeded."""
    pass


class InvalidURLError(ValueError):
    """Invalid YouTube URL."""
    pass


# =============================================================================
# MAIN EXTRACTOR CLASS
# =============================================================================

class YouTubeCommentExtractor:
    """
    Extracts comments and metadata from YouTube videos.

    Usage:
        extractor = YouTubeCommentExtractor(api_key)
        result = extractor.process_video(
            "https://youtube.com/watch?v=VIDEO_ID",
            filter_spam=True,
            min_likes=5
        )

        # Access results
        print(f"Title: {result.metadata.title}")
        print(f"Comments: {len(result.comments)}")
        print(f"Spam filtered: {len(result.spam_comments)}")
    """

    def __init__(
        self,
        api_key: str,
        spam_threshold: float = 0.5,
        blacklist_patterns: Optional[List[str]] = None,
        whitelist_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize the YouTube Comment Extractor.

        Args:
            api_key: YouTube Data API v3 key
            spam_threshold: Spam detection threshold (0.0-1.0)
                           Lower = stricter filtering
                           Higher = more permissive
            blacklist_patterns: List of patterns to always flag as spam
            whitelist_patterns: List of patterns to always allow through
        """
        self.api_key = api_key
        self._youtube: Optional[Resource] = None
        self.spam_detector = SpamDetector(
            threshold=spam_threshold,
            blacklist_patterns=blacklist_patterns,
            whitelist_patterns=whitelist_patterns,
        )

    @property
    def youtube(self) -> Resource:
        """Lazy initialization of YouTube API client."""
        if self._youtube is None:
            self._youtube = build(
                YOUTUBE_API_SERVICE_NAME,
                YOUTUBE_API_VERSION,
                developerKey=self.api_key
            )
        return self._youtube

    def get_video_id(self, url: str) -> Optional[str]:
        """
        Extract video ID from a YouTube URL.

        Args:
            url: YouTube URL in any supported format

        Returns:
            Video ID (11 characters) or None if invalid
        """
        return URLValidator.extract_video_id(url)

    def fetch_video_details(self, video_id: str) -> VideoMetadata:
        """
        Fetch video metadata from YouTube API.

        Args:
            video_id: YouTube video ID (11 characters)

        Returns:
            VideoMetadata object

        Raises:
            VideoNotFoundError: If video doesn't exist
            YouTubeAPIError: For other API errors
        """
        try:
            request = self.youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            )
            response = request.execute()

            if not response.get("items"):
                raise VideoNotFoundError(f"Video not found: {video_id}")

            item = response["items"][0]
            snippet = item["snippet"]
            stats = item.get("statistics", {})

            return VideoMetadata(
                video_id=video_id,
                title=snippet.get("title", ""),
                published_at=snippet.get("publishedAt", ""),
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                comment_count=int(stats.get("commentCount", 0)),
                channel_id=snippet.get("channelId", ""),
                url=f"https://www.youtube.com/watch?v={video_id}",
            )

        except HttpError as e:
            self._handle_http_error(e, f"fetching video {video_id}")
            raise  # Re-raise if not handled

    def fetch_comments(
        self,
        video_id: str,
        creator_channel_id: str = "",
        max_results: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        filter_spam: bool = False,
        min_likes: int = 0,
        exclude_creator: bool = False,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        filter_words: Optional[List[str]] = None,
    ) -> Tuple[List[Comment], List[SpamComment]]:
        """
        Fetch comments for a video with optional filtering.

        Args:
            video_id: YouTube video ID
            creator_channel_id: Channel ID of video creator (for exclude_creator)
            max_results: Maximum comments to fetch (None for all)
            progress_callback: Called with comment count as progress updates
            filter_spam: Whether to filter spam comments
            min_likes: Minimum likes threshold
            exclude_creator: Whether to exclude creator's comments
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)
            filter_words: List of words to filter comments (OR logic, whole-word match)

        Returns:
            Tuple of (comments, spam_comments)
        """
        comments: List[Comment] = []
        spam_comments: List[SpamComment] = []

        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=YOUTUBE_COMMENTS_PER_PAGE,
                textFormat="plainText",
                order="relevance"
            )

            while request:
                if max_results and len(comments) >= max_results:
                    break

                response = request.execute()

                for item in response.get("items", []):
                    comment = self._parse_comment(item, video_id, creator_channel_id)

                    # Apply filters (order: creator, likes, date, words, then spam)
                    if exclude_creator and comment.is_creator:
                        continue

                    if comment.like_count < min_likes:
                        continue

                    if not self._passes_date_filter(comment.published_at, date_from, date_to):
                        continue

                    # Apply words filter (whole-word, case-insensitive, OR logic)
                    if filter_words and not WordsFilterValidator.matches_any(comment.text, filter_words):
                        continue

                    # Apply spam filter last - only on comments that passed all other filters
                    if filter_spam:
                        spam_result = self.spam_detector.analyze(
                            comment.text,
                            comment.author_name,
                            comment.like_count
                        )
                        if spam_result.is_spam:
                            spam_comments.append(self._create_spam_comment(
                                comment, spam_result
                            ))
                            continue

                    comments.append(comment)

                    if max_results and len(comments) >= max_results:
                        break

                if progress_callback:
                    progress_callback(len(comments))

                # Get next page
                if "nextPageToken" in response:
                    time.sleep(API_DELAY_BETWEEN_PAGES)
                    request = self.youtube.commentThreads().list(
                        part="snippet",
                        videoId=video_id,
                        maxResults=YOUTUBE_COMMENTS_PER_PAGE,
                        textFormat="plainText",
                        pageToken=response["nextPageToken"],
                        order="relevance"
                    )
                else:
                    break

        except HttpError as e:
            self._handle_http_error(e, f"fetching comments for {video_id}")

        return comments, spam_comments

    def process_video(
        self,
        video_url: str,
        max_results: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        filter_spam: bool = False,
        min_likes: int = 0,
        sort_by: str = "likes",
        exclude_creator: bool = False,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        filter_words: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process a video URL and return metadata and comments.

        This is the main entry point for extracting video data.
        Returns dictionaries for backward compatibility.

        Args:
            video_url: YouTube video URL
            max_results: Maximum comments to fetch
            progress_callback: Progress callback function
            filter_spam: Whether to filter spam
            min_likes: Minimum likes threshold
            sort_by: Sort method ("likes", "date_desc", "date_asc")
            exclude_creator: Exclude creator comments
            date_from: Start date filter
            date_to: End date filter
            filter_words: List of words to filter comments (OR logic, whole-word match)

        Returns:
            Tuple of (metadata_dict, comments_list, spam_list)

        Raises:
            InvalidURLError: If URL is not a valid YouTube URL
            VideoNotFoundError: If video doesn't exist
            YouTubeAPIError: For API errors
        """
        # Extract video ID
        video_id = self.get_video_id(video_url)
        if not video_id:
            raise InvalidURLError(f"Invalid YouTube URL: {video_url}")

        # Fetch metadata
        metadata = self.fetch_video_details(video_id)

        # Fetch comments
        comments, spam_comments = self.fetch_comments(
            video_id=video_id,
            creator_channel_id=metadata.channel_id,
            max_results=max_results,
            progress_callback=progress_callback,
            filter_spam=filter_spam,
            min_likes=min_likes,
            exclude_creator=exclude_creator,
            date_from=date_from,
            date_to=date_to,
            filter_words=filter_words,
        )

        # Update spam count in metadata
        metadata.spam_filtered = len(spam_comments)

        # Sort comments
        comments = self._sort_comments(comments, sort_by)
        spam_comments.sort(key=lambda x: x.spam_score, reverse=True)

        # Convert to dictionaries for backward compatibility
        metadata_dict = metadata.to_dict()
        comments_list = [c.to_dict(include_is_creator=not exclude_creator) for c in comments]
        spam_list = [s.to_dict() for s in spam_comments]

        return metadata_dict, comments_list, spam_list

    def save_to_csv(
        self,
        metadata_list: List[Dict[str, Any]],
        comments_list: List[Dict[str, Any]],
        base_filename: str,
        spam_list: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Save data to CSV files.

        Creates separate files for metadata, comments, and spam.

        Args:
            metadata_list: List of video metadata dictionaries
            comments_list: List of comment dictionaries
            base_filename: Base filename (without extension)
            spam_list: Optional list of spam comment dictionaries

        Returns:
            Base filename used
        """
        encoding = "utf-8-sig"  # BOM for Excel compatibility

        if metadata_list:
            df_meta = pd.DataFrame(metadata_list)
            df_meta.to_csv(f"{base_filename}_metadata.csv", index=False, encoding=encoding)

        if comments_list:
            df_comments = pd.DataFrame(comments_list)
            df_comments.to_csv(f"{base_filename}_comments.csv", index=False, encoding=encoding)

        if spam_list:
            df_spam = pd.DataFrame(spam_list)
            df_spam.to_csv(f"{base_filename}_spam.csv", index=False, encoding=encoding)

        return base_filename

    def save_to_excel(
        self,
        metadata_list: List[Dict[str, Any]],
        comments_list: List[Dict[str, Any]],
        filename: str,
        spam_list: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Save data to Excel file with multiple sheets.

        Args:
            metadata_list: List of video metadata dictionaries
            comments_list: List of comment dictionaries
            filename: Output filename
            spam_list: Optional list of spam comment dictionaries

        Returns:
            Filename used
        """
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            if metadata_list:
                df_meta = pd.DataFrame(metadata_list)
                df_meta.to_excel(writer, sheet_name="Metadata", index=False)

            if comments_list:
                df_comments = pd.DataFrame(comments_list)
                df_comments.to_excel(writer, sheet_name="Comments", index=False)

            if spam_list:
                df_spam = pd.DataFrame(spam_list)
                df_spam.to_excel(writer, sheet_name="Flagged Spam", index=False)

        return filename

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _parse_comment(
        self,
        item: Dict[str, Any],
        video_id: str,
        creator_channel_id: str,
    ) -> Comment:
        """Parse a comment from API response."""
        top_comment = item["snippet"]["topLevelComment"]["snippet"]

        author_channel_info = top_comment.get("authorChannelId")
        author_channel_id = (
            author_channel_info.get("value", "")
            if isinstance(author_channel_info, dict)
            else ""
        )

        is_creator = (
            author_channel_id == creator_channel_id
            if creator_channel_id
            else False
        )

        return Comment(
            video_id=video_id,
            author_name=top_comment.get("authorDisplayName", ""),
            author_channel_id=author_channel_id,
            text=top_comment.get("textDisplay", ""),
            published_at=top_comment.get("publishedAt", ""),
            like_count=top_comment.get("likeCount", 0),
            reply_count=item["snippet"].get("totalReplyCount", 0),
            is_creator=is_creator,
        )

    def _create_spam_comment(self, comment: Comment, result: SpamResult) -> SpamComment:
        """Create a SpamComment from a Comment and SpamResult."""
        return SpamComment(
            video_id=comment.video_id,
            author_name=comment.author_name,
            text=comment.text,
            published_at=comment.published_at,
            like_count=comment.like_count,
            spam_score=result.score,
            spam_reason=result.reason,
            spam_category=result.primary_category.value if result.primary_category else "",
            had_obfuscation=result.had_obfuscation,
        )

    def _passes_date_filter(
        self,
        published_at: str,
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        """Check if comment passes date filter."""
        if not date_from and not date_to:
            return True

        comment_date = published_at[:10]  # Extract YYYY-MM-DD

        if date_from and comment_date < date_from:
            return False

        if date_to and comment_date > date_to:
            return False

        return True

    def _sort_comments(self, comments: List[Comment], sort_by: str) -> List[Comment]:
        """Sort comments by specified method."""
        if sort_by == SortOption.LIKES.value or sort_by == "likes":
            return sorted(comments, key=lambda x: x.like_count, reverse=True)
        elif sort_by == SortOption.DATE_NEWEST.value or sort_by == "date_desc":
            return sorted(comments, key=lambda x: x.published_at, reverse=True)
        elif sort_by == SortOption.DATE_OLDEST.value or sort_by == "date_asc":
            return sorted(comments, key=lambda x: x.published_at, reverse=False)
        return comments

    def _handle_http_error(self, error: HttpError, context: str) -> None:
        """Handle HTTP errors from YouTube API."""
        status = error.resp.status
        content = error.content.decode("utf-8") if error.content else ""

        if status == 403:
            if "commentsDisabled" in content or "disabled comments" in content.lower():
                raise CommentsDisabledError("Comments are disabled for this video")
            elif "quotaExceeded" in content.lower():
                raise QuotaExceededError("API quota exceeded. Try again tomorrow.")
            else:
                raise YouTubeAPIError(f"Access forbidden (403): Check API key permissions")

        elif status == 404:
            raise VideoNotFoundError(f"Video not found")

        else:
            raise YouTubeAPIError(f"YouTube API error ({status}): {content[:200]}")
