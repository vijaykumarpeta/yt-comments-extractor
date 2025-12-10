"""
YouTube Comment Extractor - Desktop Application.

A modern GUI application for extracting, filtering, and analyzing
YouTube comments with advanced spam detection.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from core.constants import (
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
    COLORS,
    LOG_COLORS,
    LOG_ICONS,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    DIALOG_WIDTH,
    DIALOG_HEIGHT,
    API_DELAY_BETWEEN_VIDEOS_MIN,
    API_DELAY_BETWEEN_VIDEOS_MAX,
    SortOption,
)
from core.settings import SettingsManager, AppSettings
from core.validators import (
    URLValidator,
    DateValidator,
    APIKeyValidator,
    MinLikesValidator,
    MaxCommentsValidator,
    WordsFilterValidator,
)
from extractor import YouTubeCommentExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress Google API client cache warning
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

# Configure CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FetchState:
    """State for the fetch operation."""
    is_fetching: bool = False
    cancel_event: threading.Event = None

    def __post_init__(self):
        if self.cancel_event is None:
            self.cancel_event = threading.Event()

    def start(self) -> None:
        """Start a new fetch operation."""
        self.is_fetching = True
        self.cancel_event.clear()

    def stop(self) -> None:
        """Stop the fetch operation."""
        self.is_fetching = False
        self.cancel_event.clear()

    def request_cancel(self) -> None:
        """Request cancellation of the fetch operation."""
        self.cancel_event.set()

    @property
    def cancel_requested(self) -> bool:
        """Check if cancellation was requested."""
        return self.cancel_event.is_set()


# =============================================================================
# MAIN APPLICATION CLASS
# =============================================================================

class App(ctk.CTk):
    """Main application window."""

    SIDEBAR_WIDTH = 280

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title(APP_NAME)
        self.geometry(f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(fg_color=COLORS["bg_dark"])

        # Grid configuration - header on top, sidebar + main content below
        self.grid_columnconfigure(0, weight=0)  # Sidebar - fixed width
        self.grid_columnconfigure(1, weight=1)  # Main content - expandable
        self.grid_rowconfigure(0, weight=0)  # Header - fixed height
        self.grid_rowconfigure(1, weight=1)  # Content area - expandable

        # State
        self.settings_manager = SettingsManager()
        self.extractor: Optional[YouTubeCommentExtractor] = None
        self.fetch_state = FetchState()

        # Data storage (protected by lock for thread safety)
        self._data_lock = threading.Lock()
        self.all_metadata: List[Dict[str, Any]] = []
        self.all_comments: List[Dict[str, Any]] = []
        self.all_spam: List[Dict[str, Any]] = []

        # Custom filter patterns
        self._blacklist_patterns: str = ""
        self._whitelist_patterns: str = ""

        # Build UI
        self._create_header()
        self._create_sidebar()
        self._create_main_content()

        # Bind keyboard shortcuts
        self.bind("<Control-Return>", lambda e: self.start_fetching())
        self.bind("<Control-s>", lambda e: self.export_csv())
        self.bind("<Control-e>", lambda e: self.export_excel())

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Load settings
        self._load_settings()

    # =========================================================================
    # HEADER CREATION
    # =========================================================================

    def _create_header(self) -> None:
        """Create the top header with app name and description."""
        self.header_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_card"],
            corner_radius=0,
            height=80
        )
        self.header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.header_frame.grid_propagate(False)

        # Header content
        header_content = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_content.pack(fill="both", expand=True, padx=30, pady=15)

        # App title
        title_label = ctk.CTkLabel(
            header_content,
            text=f"📺 {APP_NAME}",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title_label.pack(anchor="w")

        # Subtitle
        subtitle_label = ctk.CTkLabel(
            header_content,
            text=f"{APP_DESCRIPTION}",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"]
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

    # =========================================================================
    # SIDEBAR CREATION
    # =========================================================================

    def _create_sidebar(self) -> None:
        """Create the left sidebar with all settings."""
        self.sidebar = ctk.CTkFrame(
            self,
            width=self.SIDEBAR_WIDTH,
            fg_color=COLORS["bg_card"],
            corner_radius=0
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Sidebar scrollable content
        self.sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent_secondary"]
        )
        self.sidebar_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # API Key section
        self._create_api_section()

        # Filters section
        self._create_filters_section()

        # Date Range section
        self._create_date_section()

        # Custom Filters section
        self._create_custom_filters_section()

        # Version at bottom
        self._create_sidebar_footer()

    def _create_section_label(self, parent: ctk.CTkFrame, text: str, first: bool = False) -> None:
        """Create a section label with divider."""
        if not first:
            divider = ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1)
            divider.pack(fill="x", padx=20, pady=(15, 10))

        label = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        label.pack(anchor="w", padx=20, pady=(15 if first else 0, 10))

    def _create_api_section(self) -> None:
        """Create API key input section in sidebar."""
        self._create_section_label(self.sidebar_scroll, "API KEY", first=True)

        api_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        api_frame.pack(fill="x", padx=20)

        # API key entry with toggle button
        entry_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
        entry_frame.pack(fill="x")
        entry_frame.grid_columnconfigure(0, weight=1)

        self.api_key_entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="Enter API key",
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6,
            show="*"
        )
        self.api_key_entry.grid(row=0, column=0, sticky="ew")

        self.api_key_visible = False
        self.toggle_api_key_button = ctk.CTkButton(
            entry_frame,
            text="👁",
            width=36,
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=6,
            command=self._toggle_api_key_visibility
        )
        self.toggle_api_key_button.grid(row=0, column=1, padx=(6, 0))

        # Storage info
        storage_info = self.settings_manager.get_storage_info()
        info_text = "🔒 Secure" if "keyring" in storage_info else "⚠️ File"
        self.storage_label = ctk.CTkLabel(
            api_frame,
            text=info_text,
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        )
        self.storage_label.pack(anchor="w", pady=(4, 0))

    def _create_filters_section(self) -> None:
        """Create filters section in sidebar."""
        self._create_section_label(self.sidebar_scroll, "FILTERS")

        filters_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        filters_frame.pack(fill="x", padx=20)

        # Spam filter toggle
        spam_row = ctk.CTkFrame(filters_frame, fg_color="transparent")
        spam_row.pack(fill="x", pady=(0, 8))

        self.spam_filter_var = ctk.BooleanVar(value=True)
        self.spam_filter_checkbox = ctk.CTkSwitch(
            spam_row,
            text="Filter Spam",
            variable=self.spam_filter_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
            progress_color=COLORS["accent"],
            button_color=COLORS["text_primary"],
            button_hover_color=COLORS["text_secondary"],
            command=self._on_spam_filter_toggle
        )
        self.spam_filter_checkbox.pack(side="left")

        # Spam threshold
        threshold_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        threshold_frame.pack(fill="x", pady=(0, 12))

        threshold_label_row = ctk.CTkFrame(threshold_frame, fg_color="transparent")
        threshold_label_row.pack(fill="x")

        self.spam_threshold_label = ctk.CTkLabel(
            threshold_label_row,
            text="Sensitivity",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"]
        )
        self.spam_threshold_label.pack(side="left")

        self.spam_threshold_value_label = ctk.CTkLabel(
            threshold_label_row,
            text="Moderate",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent"]
        )
        self.spam_threshold_value_label.pack(side="right")

        self.spam_threshold_var = ctk.DoubleVar(value=0.5)
        self.spam_threshold_slider = ctk.CTkSlider(
            threshold_frame,
            from_=0.2,
            to=0.8,
            number_of_steps=12,
            variable=self.spam_threshold_var,
            height=14,
            progress_color=COLORS["accent"],
            button_color=COLORS["text_primary"],
            button_hover_color=COLORS["accent_hover"],
            fg_color=COLORS["bg_input"],
            command=self._on_spam_threshold_change
        )
        self.spam_threshold_slider.pack(fill="x", pady=(4, 0))

        # Exclude creator toggle
        self.exclude_creator_var = ctk.BooleanVar(value=False)
        self.exclude_creator_checkbox = ctk.CTkSwitch(
            filters_frame,
            text="Exclude Creator",
            variable=self.exclude_creator_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
            progress_color=COLORS["accent"],
            button_color=COLORS["text_primary"],
            button_hover_color=COLORS["text_secondary"]
        )
        self.exclude_creator_checkbox.pack(anchor="w", pady=(0, 12))

        # Min likes
        min_likes_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        min_likes_frame.pack(fill="x", pady=(0, 12))

        min_likes_label = ctk.CTkLabel(
            min_likes_frame,
            text="Min Likes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"]
        )
        min_likes_label.pack(side="left")

        self.min_likes_entry = ctk.CTkEntry(
            min_likes_frame,
            width=70,
            height=32,
            placeholder_text="0",
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6,
            justify="center"
        )
        self.min_likes_entry.pack(side="right")
        self.min_likes_entry.insert(0, "0")

        # Max comments
        max_comments_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        max_comments_frame.pack(fill="x", pady=(0, 12))

        max_comments_label = ctk.CTkLabel(
            max_comments_frame,
            text="Max Comments",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"]
        )
        max_comments_label.pack(side="left")

        self.max_comments_entry = ctk.CTkEntry(
            max_comments_frame,
            width=70,
            height=32,
            placeholder_text="All",
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6,
            justify="center"
        )
        self.max_comments_entry.pack(side="right")

        max_comments_hint = ctk.CTkLabel(
            filters_frame,
            text="Per video, leave empty for all",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        )
        max_comments_hint.pack(anchor="w", pady=(0, 12))

        # Sort by
        sort_frame = ctk.CTkFrame(filters_frame, fg_color="transparent")
        sort_frame.pack(fill="x", pady=(0, 12))

        sort_label = ctk.CTkLabel(
            sort_frame,
            text="Sort By",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"]
        )
        sort_label.pack(side="left")

        self.sort_var = ctk.StringVar(value="Likes")
        self.sort_dropdown = ctk.CTkOptionMenu(
            sort_frame,
            values=["Likes", "Date (Newest)", "Date (Oldest)"],
            variable=self.sort_var,
            width=120,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent_secondary"],
            button_hover_color=COLORS["accent"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["accent_secondary"],
            corner_radius=6
        )
        self.sort_dropdown.pack(side="right")

    def _create_date_section(self) -> None:
        """Create date range section in sidebar."""
        self._create_section_label(self.sidebar_scroll, "DATE RANGE")

        date_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        date_frame.pack(fill="x", padx=20)

        # From date
        from_frame = ctk.CTkFrame(date_frame, fg_color="transparent")
        from_frame.pack(fill="x", pady=(0, 8))

        from_label = ctk.CTkLabel(
            from_frame,
            text="From",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
            width=50,
            anchor="w"
        )
        from_label.pack(side="left")

        self.from_date_entry = ctk.CTkEntry(
            from_frame,
            placeholder_text="YYYY-MM-DD",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6
        )
        self.from_date_entry.pack(side="right", fill="x", expand=True)

        # To date
        to_frame = ctk.CTkFrame(date_frame, fg_color="transparent")
        to_frame.pack(fill="x")

        to_label = ctk.CTkLabel(
            to_frame,
            text="To",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
            width=50,
            anchor="w"
        )
        to_label.pack(side="left")

        self.to_date_entry = ctk.CTkEntry(
            to_frame,
            placeholder_text="YYYY-MM-DD",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6
        )
        self.to_date_entry.pack(side="right", fill="x", expand=True)

        # Hint
        hint_label = ctk.CTkLabel(
            date_frame,
            text="Leave empty for no limit",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        )
        hint_label.pack(anchor="w", pady=(6, 0))

    def _create_custom_filters_section(self) -> None:
        """Create custom filters (blacklist/whitelist) section in sidebar."""
        self._create_section_label(self.sidebar_scroll, "CUSTOM FILTERS")

        custom_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent")
        custom_frame.pack(fill="x", padx=20)

        # Blacklist button
        self.blacklist_button = ctk.CTkButton(
            custom_frame,
            text="🚫 Blacklist Patterns",
            command=self._open_blacklist_dialog,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=6,
            anchor="w"
        )
        self.blacklist_button.pack(fill="x", pady=(0, 8))

        # Whitelist button
        self.whitelist_button = ctk.CTkButton(
            custom_frame,
            text="✓ Whitelist Patterns",
            command=self._open_whitelist_dialog,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=6,
            anchor="w"
        )
        self.whitelist_button.pack(fill="x")

        # Pattern count label
        self.pattern_count_label = ctk.CTkLabel(
            custom_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        )
        self.pattern_count_label.pack(anchor="w", pady=(6, 0))

    def _create_sidebar_footer(self) -> None:
        """Create sidebar footer with version."""
        footer_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer_frame.pack(side="bottom", fill="x", padx=20, pady=15)

        version_label = ctk.CTkLabel(
            footer_frame,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        )
        version_label.pack(side="left")

        shortcuts_label = ctk.CTkLabel(
            footer_frame,
            text="Ctrl+Enter: Fetch",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        )
        shortcuts_label.pack(side="right")

    # =========================================================================
    # MAIN CONTENT CREATION
    # =========================================================================

    def _create_main_content(self) -> None:
        """Create the main content area."""
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=1, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)  # Log section expands

        self._create_url_section()
        self._create_progress_section()
        self._create_log_section()

    def _create_url_section(self) -> None:
        """Create URL input and action buttons section."""
        url_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"]
        )
        url_card.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        url_card.grid_columnconfigure(0, weight=1)

        # URL input area
        url_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        url_frame.pack(fill="x", padx=20, pady=(20, 15))

        url_label = ctk.CTkLabel(
            url_frame,
            text="📺 Video URLs",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        url_label.pack(anchor="w", pady=(0, 10))

        self.url_entry = ctk.CTkTextbox(
            url_frame,
            height=100,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8
        )
        self.url_entry.pack(fill="x")

        # Placeholder handling
        self._url_placeholder = "Paste YouTube URLs here (one per line)...\n\nSupported formats:\n• youtube.com/watch?v=...\n• youtu.be/...\n• youtube.com/shorts/..."
        self.url_entry.insert("1.0", self._url_placeholder)
        self.url_entry.configure(text_color=COLORS["text_muted"])
        self.url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self.url_entry.bind("<FocusOut>", self._on_url_focus_out)
        self.url_entry.bind("<KeyRelease>", self._validate_urls_live)

        # URL status
        self.url_status = ctk.CTkLabel(
            url_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        )
        self.url_status.pack(anchor="e", pady=(5, 0))

        # Filter words section
        filter_words_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        filter_words_frame.pack(fill="x", padx=20, pady=(0, 15))

        filter_words_header = ctk.CTkFrame(filter_words_frame, fg_color="transparent")
        filter_words_header.pack(fill="x")

        filter_words_label = ctk.CTkLabel(
            filter_words_header,
            text="🔍 Filter Words",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        filter_words_label.pack(side="left")

        filter_words_hint = ctk.CTkLabel(
            filter_words_header,
            text="Comma-separated, matches any word",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        )
        filter_words_hint.pack(side="right")

        self.filter_words_entry = ctk.CTkEntry(
            filter_words_frame,
            height=36,
            placeholder_text="e.g., python, tutorial, beginner",
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            corner_radius=6
        )
        self.filter_words_entry.pack(fill="x", pady=(8, 0))

        # Action buttons
        action_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Fetch button (primary)
        self.fetch_button = ctk.CTkButton(
            action_frame,
            text="▶  Fetch Comments",
            command=self.start_fetching,
            width=160,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8
        )
        self.fetch_button.pack(side="left")

        # Cancel button (hidden by default)
        self.cancel_button = ctk.CTkButton(
            action_frame,
            text="⏹  Cancel",
            command=self.cancel_fetching,
            width=100,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["error"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8
        )
        # Don't pack yet

        # Export buttons (right side)
        self.export_excel_button = ctk.CTkButton(
            action_frame,
            text="📊 Excel",
            command=self.export_excel,
            width=90,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["accent_secondary"],
            hover_color=COLORS["border"],
            corner_radius=8,
            state="disabled"
        )
        self.export_excel_button.pack(side="right")

        self.export_button = ctk.CTkButton(
            action_frame,
            text="📥 CSV",
            command=self.export_csv,
            width=90,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["accent_secondary"],
            hover_color=COLORS["border"],
            corner_radius=8,
            state="disabled"
        )
        self.export_button.pack(side="right", padx=(0, 10))

    def _create_progress_section(self) -> None:
        """Create the progress indicator section."""
        self.progress_section = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.progress_section.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        # Status row
        status_row = ctk.CTkFrame(self.progress_section, fg_color="transparent")
        status_row.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            status_row,
            text="Ready to fetch comments",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.status_label.pack(side="left")

        self.stats_label = ctk.CTkLabel(
            status_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.stats_label.pack(side="right")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_section,
            height=6,
            corner_radius=3,
            fg_color=COLORS["bg_card"],
            progress_color=COLORS["accent"]
        )
        self.progress_bar.pack(fill="x", pady=(8, 0))
        self.progress_bar.set(0)

    def _create_log_section(self) -> None:
        """Create the activity log section."""
        self.log_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"]
        )
        self.log_card.grid(row=2, column=0, sticky="nsew")
        self.log_card.grid_rowconfigure(1, weight=1)
        self.log_card.grid_columnconfigure(0, weight=1)

        # Log header
        log_header = ctk.CTkFrame(self.log_card, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))

        log_title = ctk.CTkLabel(
            log_header,
            text="📋 Activity Log",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        log_title.pack(side="left")

        # Stats in header
        self.footer_stats = ctk.CTkLabel(
            log_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        )
        self.footer_stats.pack(side="right", padx=(0, 10))

        # Clear button
        self.clear_log_button = ctk.CTkButton(
            log_header,
            text="Clear",
            width=60,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_muted"],
            corner_radius=6,
            command=self.clear_log
        )
        self.clear_log_button.pack(side="right")

        # Log content
        self.log_frame = ctk.CTkScrollableFrame(
            self.log_card,
            fg_color=COLORS["bg_input"],
            corner_radius=8
        )
        self.log_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))

    # =========================================================================
    # DIALOG METHODS
    # =========================================================================

    def _open_blacklist_dialog(self) -> None:
        """Open dialog to edit blacklist patterns."""
        result = self._open_pattern_dialog(
            title="Blacklist Patterns",
            description="Comments containing these patterns will always be flagged as spam.\nEnter one pattern per line (case-insensitive).",
            current_patterns=self._blacklist_patterns,
            icon="🚫"
        )
        if result is not None:
            self._blacklist_patterns = result
            self._update_filter_counts()

    def _open_whitelist_dialog(self) -> None:
        """Open dialog to edit whitelist patterns."""
        result = self._open_pattern_dialog(
            title="Whitelist Patterns",
            description="Comments containing these patterns will always be allowed through.\nEnter one pattern per line (case-insensitive).",
            current_patterns=self._whitelist_patterns,
            icon="✓"
        )
        if result is not None:
            self._whitelist_patterns = result
            self._update_filter_counts()

    def _open_pattern_dialog(
        self,
        title: str,
        description: str,
        current_patterns: str,
        icon: str
    ) -> Optional[str]:
        """Open a dialog for editing patterns. Returns new patterns or None if cancelled."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - DIALOG_WIDTH) // 2
        y = self.winfo_y() + (self.winfo_height() - DIALOG_HEIGHT) // 2
        dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}+{x}+{y}")

        result = {"value": None}

        # Header
        header_frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_card"], corner_radius=0)
        header_frame.pack(fill="x")

        header_label = ctk.CTkLabel(
            header_frame,
            text=f"{icon} {title}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        header_label.pack(pady=15, padx=20, anchor="w")

        # Description
        desc_label = ctk.CTkLabel(
            dialog,
            text=description,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            justify="left"
        )
        desc_label.pack(pady=(15, 10), padx=20, anchor="w")

        # Text area
        text_area = ctk.CTkTextbox(
            dialog,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8
        )
        text_area.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Insert current patterns
        if current_patterns:
            text_area.insert("1.0", current_patterns)

        # Buttons frame
        buttons_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_save():
            result["value"] = text_area.get("1.0", "end").strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            command=on_cancel,
            width=100,
            height=36,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=6
        )
        cancel_btn.pack(side="right", padx=(10, 0))

        save_btn = ctk.CTkButton(
            buttons_frame,
            text="Save",
            command=on_save,
            width=100,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=6
        )
        save_btn.pack(side="right")

        # Wait for dialog to close
        dialog.wait_window()
        return result["value"]

    def _update_filter_counts(self) -> None:
        """Update the count label showing number of patterns."""
        blacklist_count = len([p for p in self._blacklist_patterns.split('\n') if p.strip()])
        whitelist_count = len([p for p in self._whitelist_patterns.split('\n') if p.strip()])

        parts = []
        if blacklist_count > 0:
            parts.append(f"{blacklist_count} blacklisted")
        if whitelist_count > 0:
            parts.append(f"{whitelist_count} whitelisted")

        self.pattern_count_label.configure(text=" • ".join(parts) if parts else "")

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_closing(self) -> None:
        """Handle window close event - cancel any running operations."""
        if self.fetch_state.is_fetching:
            self.fetch_state.request_cancel()
            self.after(100, self.destroy)
        else:
            self.destroy()

    def _toggle_api_key_visibility(self) -> None:
        """Toggle API key visibility."""
        self.api_key_visible = not self.api_key_visible
        if self.api_key_visible:
            self.api_key_entry.configure(show="")
            self.toggle_api_key_button.configure(text="🔒")
        else:
            self.api_key_entry.configure(show="*")
            self.toggle_api_key_button.configure(text="👁")

    def _on_spam_filter_toggle(self) -> None:
        """Handle spam filter toggle - enable/disable threshold slider."""
        enabled = self.spam_filter_var.get()
        state = "normal" if enabled else "disabled"

        self.spam_threshold_slider.configure(state=state)
        self.spam_threshold_label.configure(
            text_color=COLORS["text_secondary"] if enabled else COLORS["text_muted"]
        )
        self.spam_threshold_value_label.configure(
            text_color=COLORS["accent"] if enabled else COLORS["text_muted"]
        )

    def _on_spam_threshold_change(self, value: float) -> None:
        """Update threshold label based on slider value."""
        if value >= 0.65:
            label = "Light"
        elif value >= 0.5:
            label = "Moderate"
        elif value >= 0.4:
            label = "Aggressive"
        else:
            label = "Strict"

        self.spam_threshold_value_label.configure(text=label)

    def _on_url_focus_in(self, event: Any) -> None:
        """Clear placeholder when URL entry is focused."""
        current_text = self.url_entry.get("1.0", "end").strip()
        if current_text == self._url_placeholder.strip():
            self.url_entry.delete("1.0", "end")
            self.url_entry.configure(text_color=COLORS["text_primary"])

    def _on_url_focus_out(self, event: Any) -> None:
        """Restore placeholder if URL entry is empty."""
        current_text = self.url_entry.get("1.0", "end").strip()
        if not current_text:
            self.url_entry.insert("1.0", self._url_placeholder)
            self.url_entry.configure(text_color=COLORS["text_muted"])

    def _validate_urls_live(self, event: Any = None) -> None:
        """Validate URLs as user types."""
        current_text = self.url_entry.get("1.0", "end").strip()

        if current_text == self._url_placeholder.strip() or not current_text:
            self.url_status.configure(text="", text_color=COLORS["text_muted"])
            return

        valid_count, invalid_count, status_msg = URLValidator.get_validation_summary(current_text)

        if valid_count == 0:
            color = COLORS["warning"]
        elif invalid_count == 0:
            color = COLORS["success"]
        else:
            color = COLORS["warning"]

        self.url_status.configure(text=status_msg, text_color=color)

    # =========================================================================
    # SETTINGS MANAGEMENT
    # =========================================================================

    def _load_settings(self) -> None:
        """Load settings from storage."""
        try:
            settings = self.settings_manager.load()

            if settings.api_key:
                self.api_key_entry.insert(0, settings.api_key)

            self.spam_filter_var.set(settings.filter_spam)
            self.spam_threshold_var.set(settings.spam_threshold)
            self._on_spam_threshold_change(settings.spam_threshold)
            self._on_spam_filter_toggle()
            self.exclude_creator_var.set(settings.exclude_creator)

            self.min_likes_entry.delete(0, "end")
            self.min_likes_entry.insert(0, str(settings.min_likes))

            # Load max comments (only if set)
            if settings.max_comments is not None:
                self.max_comments_entry.delete(0, "end")
                self.max_comments_entry.insert(0, str(settings.max_comments))

            sort_option = SortOption(settings.sort_by) if settings.sort_by else SortOption.LIKES
            self.sort_var.set(sort_option.display_name)

            # Load filter words
            if settings.filter_words:
                self.filter_words_entry.delete(0, "end")
                self.filter_words_entry.insert(0, settings.filter_words)

            self._blacklist_patterns = settings.blacklist_patterns or ""
            self._whitelist_patterns = settings.whitelist_patterns or ""
            self._update_filter_counts()

        except Exception as e:
            logger.error(f"Failed to load settings: {e}")

    def _save_settings(self) -> None:
        """Save current settings."""
        try:
            settings = AppSettings(
                api_key=self.api_key_entry.get().strip(),
                filter_spam=self.spam_filter_var.get(),
                spam_threshold=self.spam_threshold_var.get(),
                exclude_creator=self.exclude_creator_var.get(),
                min_likes=self._get_min_likes(),
                max_comments=self._get_max_comments(),
                filter_words=self.filter_words_entry.get().strip(),
                sort_by=SortOption.from_display_name(self.sort_var.get()).value,
                blacklist_patterns=self._blacklist_patterns,
                whitelist_patterns=self._whitelist_patterns,
            )
            self.settings_manager.save(settings)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            self.log_message(f"Error saving settings: {e}", "error")

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _get_min_likes(self) -> int:
        """Parse min likes value with validation."""
        value, warning = MinLikesValidator.parse(self.min_likes_entry.get())
        if warning:
            self.log_message(warning, "warning")
        return value

    def _get_max_comments(self) -> Optional[int]:
        """Parse max comments value with validation."""
        value, warning = MaxCommentsValidator.parse(self.max_comments_entry.get())
        if warning:
            self.log_message(warning, "warning")
        return value

    def _get_filter_words(self) -> List[str]:
        """Parse filter words into a list."""
        return WordsFilterValidator.parse(self.filter_words_entry.get())

    def _get_date_range(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get and validate date range."""
        from_date = DateValidator.parse(self.from_date_entry.get())
        to_date = DateValidator.parse(self.to_date_entry.get())

        result = DateValidator.validate_range(from_date, to_date)
        if not result:
            return None, None, result.error_message

        return from_date, to_date, None

    def clear_log(self) -> None:
        """Clear the activity log."""
        for widget in self.log_frame.winfo_children():
            widget.destroy()

    def _scroll_log_to_bottom(self) -> None:
        """Scroll the log frame to the bottom."""
        try:
            self.log_frame._parent_canvas.yview_moveto(1.0)
        except (AttributeError, Exception):
            pass

    def log_message(self, message: str, level: str = "info") -> None:
        """Add a message to the activity log."""
        color = LOG_COLORS.get(level, COLORS["text_secondary"])
        icon = LOG_ICONS.get(level, "→")

        entry = ctk.CTkLabel(
            self.log_frame,
            text=f" {icon}  {message}",
            font=ctk.CTkFont(size=12),
            text_color=color,
            anchor="w",
            justify="left"
        )
        entry.pack(fill="x", padx=10, pady=3)

        self.log_frame.after(10, lambda: entry.winfo_toplevel() and self._scroll_log_to_bottom())

    def _update_stats(self) -> None:
        """Update statistics display."""
        with self._data_lock:
            videos = len(self.all_metadata)
            comments = len(self.all_comments)
            spam = len(self.all_spam)

        stats_parts = [
            f"📊 {videos} video{'s' if videos != 1 else ''}",
            f"{comments:,} comment{'s' if comments != 1 else ''}"
        ]
        if spam > 0:
            stats_parts.append(f"🚫 {spam:,} spam")

        self.footer_stats.configure(text=" • ".join(stats_parts))

    # =========================================================================
    # CORE FUNCTIONALITY
    # =========================================================================

    def cancel_fetching(self) -> None:
        """Request cancellation of the fetch operation."""
        if self.fetch_state.is_fetching:
            self.fetch_state.request_cancel()
            self.status_label.configure(text="Cancelling...", text_color=COLORS["warning"])
            self.log_message("Cancellation requested...", "warning")

    def start_fetching(self) -> None:
        """Start the comment fetching process."""
        if self.fetch_state.is_fetching:
            return

        # Get and validate inputs
        api_key = self.api_key_entry.get().strip()

        current_text = self.url_entry.get("1.0", "end").strip()
        if current_text == self._url_placeholder.strip():
            current_text = ""

        valid_urls, _ = URLValidator.parse_url_list(current_text)

        # Validate API key
        api_result = APIKeyValidator.validate(api_key)
        if not api_result:
            messagebox.showerror("Invalid API Key", api_result.error_message)
            return

        # Validate URLs
        if not valid_urls:
            messagebox.showerror(
                "Missing URLs",
                "Please enter at least one valid YouTube video URL.\n\n"
                "Supported formats:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/..."
            )
            return

        # Validate date range
        date_from, date_to, date_error = self._get_date_range()
        if date_error:
            messagebox.showerror("Invalid Date Range", date_error)
            return

        # Save settings
        self._save_settings()

        # Update UI state
        self.fetch_state.start()
        self.fetch_button.pack_forget()
        self.cancel_button.pack(side="left")
        self.export_button.configure(state="disabled")
        self.export_excel_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(text="Initializing...", text_color=COLORS["text_secondary"])

        # Clear previous data
        self.clear_log()
        with self._data_lock:
            self.all_metadata = []
            self.all_comments = []
            self.all_spam = []
        self._update_stats()

        # Get custom filter patterns
        blacklist_patterns = [p.strip() for p in self._blacklist_patterns.split('\n') if p.strip()]
        whitelist_patterns = [p.strip() for p in self._whitelist_patterns.split('\n') if p.strip()]

        # Create extractor with spam threshold and custom patterns
        self.extractor = YouTubeCommentExtractor(
            api_key,
            spam_threshold=self.spam_threshold_var.get(),
            blacklist_patterns=blacklist_patterns if blacklist_patterns else None,
            whitelist_patterns=whitelist_patterns if whitelist_patterns else None,
        )

        # Get filter words
        filter_words = self._get_filter_words()
        max_comments = self._get_max_comments()

        # Log start
        self.log_message(f"Starting extraction for {len(valid_urls)} video(s)...", "info")
        if blacklist_patterns:
            self.log_message(f"Using {len(blacklist_patterns)} blacklist pattern(s)", "muted")
        if whitelist_patterns:
            self.log_message(f"Using {len(whitelist_patterns)} whitelist pattern(s)", "muted")
        if filter_words:
            self.log_message(f"Filtering for words: {', '.join(filter_words)}", "muted")
        if max_comments:
            self.log_message(f"Max {max_comments} comments per video", "muted")

        # Start fetch thread
        thread = threading.Thread(
            target=self._fetch_thread,
            args=(
                valid_urls,
                self.spam_filter_var.get(),
                self._get_min_likes(),
                SortOption.from_display_name(self.sort_var.get()).value,
                self.exclude_creator_var.get(),
                date_from,
                date_to,
                filter_words,
                max_comments,
            ),
            daemon=True
        )
        thread.start()

    def _fetch_thread(
        self,
        urls: List[str],
        filter_spam: bool,
        min_likes: int,
        sort_by: str,
        exclude_creator: bool,
        date_from: Optional[str],
        date_to: Optional[str],
        filter_words: List[str],
        max_comments: Optional[int],
    ) -> None:
        """Background thread for fetching comments."""
        total_videos = len(urls)

        try:
            for i, url in enumerate(urls):
                if self.fetch_state.cancel_requested:
                    self.after(0, lambda: self.log_message("Fetch cancelled by user", "warning"))
                    break

                video_num = i + 1
                self.after(0, lambda v=video_num, t=total_videos:
                    self.status_label.configure(
                        text=f"Processing video {v}/{t}...",
                        text_color=COLORS["text_secondary"]
                    ))
                self.after(0, lambda u=url: self.log_message(f"Fetching: {u}", "info"))

                try:
                    metadata, comments, spam = self.extractor.process_video(
                        url,
                        max_results=max_comments,
                        progress_callback=None,
                        filter_spam=filter_spam,
                        min_likes=min_likes,
                        sort_by=sort_by,
                        exclude_creator=exclude_creator,
                        date_from=date_from,
                        date_to=date_to,
                        filter_words=filter_words if filter_words else None,
                    )

                    with self._data_lock:
                        self.all_metadata.append(metadata)
                        self.all_comments.extend(comments)
                        self.all_spam.extend(spam)

                    log_msg = f"Retrieved {len(comments):,} comments"
                    if len(spam) > 0:
                        log_msg += f" (filtered {len(spam)} spam)"
                    self.after(0, lambda msg=log_msg: self.log_message(msg, "success"))
                    self.after(0, self._update_stats)

                except Exception as e:
                    error_msg = str(e)
                    if "403" in error_msg:
                        error_msg = "Comments are disabled for this video"
                    elif "404" in error_msg:
                        error_msg = "Video not found"
                    elif "quotaExceeded" in error_msg.lower():
                        error_msg = "API quota exceeded. Try again tomorrow."

                    self.after(0, lambda err=error_msg:
                        self.log_message(f"Error: {err}", "error"))

                progress = video_num / total_videos
                self.after(0, lambda p=progress: self.progress_bar.set(p))

                if i < total_videos - 1 and not self.fetch_state.cancel_requested:
                    delay = random.uniform(API_DELAY_BETWEEN_VIDEOS_MIN, API_DELAY_BETWEEN_VIDEOS_MAX)
                    self.after(0, lambda d=delay:
                        self.log_message(f"Rate limit delay: {d:.1f}s", "muted"))
                    time.sleep(delay)

            # Get counts with thread-safe access
            with self._data_lock:
                video_count = len(self.all_metadata)
                has_comments = len(self.all_comments) > 0

            if self.fetch_state.cancel_requested:
                self.after(0, lambda c=video_count: self.status_label.configure(
                    text=f"Cancelled — {c} video(s) processed",
                    text_color=COLORS["warning"]
                ))
            else:
                self.after(0, lambda c=video_count: self.status_label.configure(
                    text=f"✓ Completed — {c} video(s) processed",
                    text_color=COLORS["success"]
                ))
                self.after(0, lambda: self.log_message("Extraction complete!", "success"))

            if has_comments:
                self.after(0, lambda: self.export_button.configure(state="normal"))
                self.after(0, lambda: self.export_excel_button.configure(state="normal"))

        except Exception as e:
            logger.exception("Fetch thread error")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_label.configure(
                text="Error occurred",
                text_color=COLORS["error"]
            ))
        finally:
            self.after(0, self._reset_fetch_ui)

    def _reset_fetch_ui(self) -> None:
        """Reset UI after fetch completes or is cancelled."""
        self.fetch_state.stop()
        self.cancel_button.pack_forget()
        self.fetch_button.pack(side="left")

    def export_csv(self) -> None:
        """Export data to CSV files."""
        if not self.all_comments:
            messagebox.showwarning("No Data", "No comments to export. Fetch comments first.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Comments Data"
        )

        if filename:
            base_filename = os.path.splitext(filename)[0]
            try:
                self.extractor.save_to_csv(
                    self.all_metadata,
                    self.all_comments,
                    base_filename,
                    spam_list=self.all_spam if self.all_spam else None
                )

                files_saved = [
                    f"• {os.path.basename(base_filename)}_metadata.csv",
                    f"• {os.path.basename(base_filename)}_comments.csv"
                ]
                if self.all_spam:
                    files_saved.append(f"• {os.path.basename(base_filename)}_spam.csv")

                self.log_message(f"Exported {len(files_saved)} files", "success")
                messagebox.showinfo(
                    "Export Successful",
                    f"Files saved:\n\n" + "\n".join(files_saved)
                )
            except Exception as e:
                logger.exception("CSV export error")
                self.log_message(f"Export failed: {e}", "error")
                messagebox.showerror("Export Error", f"Failed to save files:\n{e}")

    def export_excel(self) -> None:
        """Export data to Excel file."""
        if not self.all_comments:
            messagebox.showwarning("No Data", "No comments to export. Fetch comments first.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="Save Comments Data"
        )

        if filename:
            try:
                self.extractor.save_to_excel(
                    self.all_metadata,
                    self.all_comments,
                    filename,
                    spam_list=self.all_spam if self.all_spam else None
                )

                sheets = ["Metadata", "Comments"]
                if self.all_spam:
                    sheets.append("Flagged Spam")

                self.log_message(f"Exported to: {os.path.basename(filename)}", "success")
                messagebox.showinfo(
                    "Export Successful",
                    f"Excel file saved:\n\n• {os.path.basename(filename)}\n\nSheets: {', '.join(sheets)}"
                )
            except Exception as e:
                logger.exception("Excel export error")
                self.log_message(f"Export failed: {e}", "error")
                messagebox.showerror("Export Error", f"Failed to save file:\n{e}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point for the application."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
