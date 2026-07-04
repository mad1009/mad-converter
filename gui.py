import os
import io
import threading
import multiprocessing
from pathlib import Path
import concurrent.futures
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageOps

# CRITICAL: Allow Pillow to open massive 200MB TIFFs
Image.MAX_IMAGE_PIXELS = None

VALID_EXTENSIONS = {".tiff", ".tif", ".jpg", ".jpeg", ".png", ".webp"}

# ---------------------------------------------------------
# WORKER FUNCTIONS (Multiprocessing)
# ---------------------------------------------------------
def save_closest_to_target_size(img, output_path, target_kb, image_format="WEBP"):
    target_bytes = target_kb * 1024
    low, high = 1, 100
    best_quality = 1
    best_buffer = None
    
    while low <= high:
        mid_quality = (low + high) // 2
        temp_buffer = io.BytesIO()
        img.save(temp_buffer, format=image_format, quality=mid_quality, method=6)
        file_size = temp_buffer.tell()
        
        if file_size <= target_bytes:
            best_quality = mid_quality
            best_buffer = temp_buffer.getvalue()
            low = mid_quality + 1
        else:
            high = mid_quality - 1
            
    if best_buffer is None:
        img.save(output_path, format=image_format, quality=1, method=6)
        return 1
        
    with open(output_path, "wb") as f:
        f.write(best_buffer)
        
    return best_quality

def process_single_image_task(args):
    file_path, target_dir, width, height, max_kb, crop_enabled = args
    output_path = target_dir / f"{file_path.stem}.webp"
    
    try:
        original_size = file_path.stat().st_size
        with Image.open(file_path) as img:
            if img.mode == 'RGBA':
                background = Image.new('RGBA', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # --- DYNAMIC DIMENSION HANDLING ---
            # Fall back to original image dimensions if None is provided
            actual_w = width if width is not None else img.width
            actual_h = height if height is not None else img.height

            if crop_enabled:
                optimized_img = ImageOps.fit(img, (actual_w, actual_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            else:
                img.thumbnail((actual_w, actual_h), Image.Resampling.LANCZOS)
                optimized_img = img
            
            final_quality = save_closest_to_target_size(optimized_img, output_path, max_kb, "WEBP")
                
        final_size = output_path.stat().st_size
        return True, original_size, final_size, f"✅ {file_path.name} (Q: {final_quality}%)"
    except Exception as e:
        return False, 0, 0, f"❌ {file_path.name} (Error: {e})"


# ---------------------------------------------------------
# GUI APPLICATION (DASHBOARD ARCHITECTURE)
# ---------------------------------------------------------
class ArtOptimizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Art Optimization Pipeline Pro")
        self.geometry("1200x900")
        self.minsize(1000, 750)
        ctk.set_appearance_mode("dark")
        
        # UI Colors
        self.bg_color = "#121212"
        self.sidebar_color = "#1A1A1A"
        self.card_color = "#242424"
        self.accent_color = "#3B8ED0"
        self.success_color = "#2A8C55"
        self.danger_color = "#C62828"

        self.configure(fg_color=self.bg_color)

        # --- Fonts ---
        self.font_logo = ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        self.font_h1 = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        self.font_h2 = ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        self.font_body = ctk.CTkFont(family="Segoe UI", size=14)
        self.font_mono = ctk.CTkFont(family="Consolas", size=12)

        # --- Core Grid Architecture ---
        self.grid_columnconfigure(0, weight=0) # Sidebar (Fixed)
        self.grid_columnconfigure(1, weight=1) # Main Content (Expands)
        self.grid_rowconfigure(0, weight=1)

        self.section_rows = []
        self.current_grid_row = 1

        # --- Components ---
        self.setup_sidebar()
        self.setup_main_content_area()
        self.setup_global_console()

        # Build the pages
        self.setup_batch_view()
        self.setup_custom_view()
        self.setup_guide_view()
        self.setup_converter_view()

        # Boot state
        self.select_frame("batch")
        self.log("🚀 System Boot Sequence Complete. Dashboard Ready.\n")

    # =========================================================
    # SIDEBAR NAVIGATION
    # =========================================================
    def setup_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=self.sidebar_color)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Pushes version down

        # Logo/Title
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Mad Converter", font=self.font_logo)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 40))

        # Navigation Buttons
        btn_args = {
            "corner_radius": 8, "height": 40, "border_spacing": 10, 
            "text_color": ("gray10", "gray90"), "hover_color": ("gray70", "gray30"),
            "anchor": "w", "font": self.font_body
        }

        self.btn_nav_batch = ctk.CTkButton(self.sidebar_frame, text="📂 Batch Pipeline", command=lambda: self.select_frame("batch"), **btn_args)
        self.btn_nav_batch.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        self.btn_nav_custom = ctk.CTkButton(self.sidebar_frame, text="📄 Custom Files", command=lambda: self.select_frame("custom"), **btn_args)
        self.btn_nav_custom.grid(row=2, column=0, padx=15, pady=5, sticky="ew")

        self.btn_nav_converter = ctk.CTkButton(self.sidebar_frame, text="🔄 Format Converter", command=lambda: self.select_frame("converter"), **btn_args)
        self.btn_nav_converter.grid(row=3, column=0, padx=15, pady=5, sticky="ew")

        self.btn_nav_guide = ctk.CTkButton(self.sidebar_frame, text="📖 Guide & Docs", command=lambda: self.select_frame("guide"), **btn_args)
        self.btn_nav_guide.grid(row=4, column=0, padx=15, pady=5, sticky="ew")

        # Version Footer
        self.version_label = ctk.CTkLabel(self.sidebar_frame, text="v2.0.0", text_color="gray50")
        self.version_label.grid(row=5, column=0, padx=20, pady=20, sticky="s")

    def select_frame(self, frame_name):
        # Reset button colors
        self.btn_nav_batch.configure(fg_color="transparent")
        self.btn_nav_custom.configure(fg_color="transparent")
        self.btn_nav_guide.configure(fg_color="transparent")
        self.btn_nav_converter.configure(fg_color="transparent") # <-- NEW
        # Hide all frames
        self.frame_batch.grid_remove()
        self.frame_custom.grid_remove()
        self.frame_guide.grid_remove()
        self.frame_converter.grid_remove() # <-- NEW

        # Show selected frame & highlight button
        if frame_name == "batch":
            self.frame_batch.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_batch.configure(fg_color=self.card_color)
        elif frame_name == "custom":
            self.frame_custom.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_custom.configure(fg_color=self.card_color)
        elif frame_name == "guide":
            self.frame_guide.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_guide.configure(fg_color=self.card_color)
        elif frame_name == "converter":
            self.frame_converter.grid(row=0, column=1, sticky="nsew")
            self.btn_nav_converter.configure(fg_color=self.card_color)
    # =========================================================
    # MAIN CONTENT CONTAINERS
    # =========================================================
    def setup_main_content_area(self):
            frame_args = {"fg_color": "transparent", "corner_radius": 0}
            
            self.frame_batch = ctk.CTkFrame(self, **frame_args)
            self.frame_custom = ctk.CTkFrame(self, **frame_args)
            self.frame_guide = ctk.CTkFrame(self, **frame_args)
            self.frame_converter = ctk.CTkFrame(self, **frame_args) # <-- NEW

            for f in (self.frame_batch, self.frame_custom, self.frame_guide, self.frame_converter): # <-- UPDATED
                f.grid_columnconfigure(0, weight=1)
                f.grid_rowconfigure(1, weight=1)
    # =========================================================
    # VIEW: BATCH PIPELINE
    # =========================================================
    def setup_batch_view(self):
        # Header
        ctk.CTkLabel(self.frame_batch, text="Batch Processing Pipeline", font=self.font_logo).grid(row=0, column=0, padx=30, pady=(30, 20), sticky="w")

        # Container for scrollable cards
        scroll_container = ctk.CTkScrollableFrame(self.frame_batch, fg_color="transparent")
        scroll_container.grid(row=1, column=0, sticky="nsew", padx=15)
        scroll_container.grid_columnconfigure(0, weight=1)

        # --- Card 1: Workspace ---
        card_workspace = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_workspace.grid(row=0, column=0, pady=(0, 20), sticky="ew")
        card_workspace.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_workspace, text="Workspace Setup", font=self.font_h2).grid(row=0, column=0, columnspan=4, padx=25, pady=(25, 15), sticky="w")

        # Inputs
        ctk.CTkLabel(card_workspace, text="Raw Input Directory:", font=self.font_body, text_color="gray70").grid(row=1, column=0, padx=25, pady=10, sticky="w")
        self.entry_batch_in = ctk.CTkEntry(card_workspace, height=35)
        self.entry_batch_in.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ctk.CTkButton(card_workspace, text="Browse", width=80, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_directory(self.entry_batch_in)).grid(row=1, column=2, padx=(0, 10), pady=10)
        self.btn_create_folders = ctk.CTkButton(card_workspace, text="Generate Folders", width=130, height=35, fg_color="transparent", border_width=1, border_color=self.success_color, text_color=self.success_color, hover_color="#1e3a2b", command=self.create_folder_structure)
        self.btn_create_folders.grid(row=1, column=3, padx=(0, 25), pady=10)

        ctk.CTkLabel(card_workspace, text="WebP Output Directory:", font=self.font_body, text_color="gray70").grid(row=2, column=0, padx=25, pady=(0, 25), sticky="w")
        self.entry_batch_out = ctk.CTkEntry(card_workspace, height=35)
        self.entry_batch_out.grid(row=2, column=1, padx=(0, 10), pady=(0, 25), sticky="ew")
        ctk.CTkButton(card_workspace, text="Browse", width=80, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_directory(self.entry_batch_out)).grid(row=2, column=2, padx=(0, 10), pady=(0, 25))

        # --- Card 2: Rules Engine ---
        card_rules = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_rules.grid(row=1, column=0, pady=(0, 20), sticky="ew")
        card_rules.grid_columnconfigure(0, weight=1)

        # Header inner-frame to align title and add button
        rules_header = ctk.CTkFrame(card_rules, fg_color="transparent")
        rules_header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))
        rules_header.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(rules_header, text="Optimization Rules", font=self.font_h2).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(rules_header, text="+ Add Rule", width=100, height=30, fg_color=self.sidebar_color, border_width=1, border_color="gray40", command=self.add_section_row).grid(row=0, column=1, sticky="e")

        # Dynamic Table Space
        self.table_frame = ctk.CTkFrame(card_rules, fg_color="transparent")
        self.table_frame.grid(row=1, column=0, padx=25, pady=(0, 25), sticky="ew")
        self.table_frame.grid_columnconfigure(0, weight=3) # Name
        self.table_frame.grid_columnconfigure(1, weight=1) # Width
        self.table_frame.grid_columnconfigure(2, weight=1) # Height
        self.table_frame.grid_columnconfigure(3, weight=1) # KB
        self.table_frame.grid_columnconfigure(4, weight=0) # Delete
        
        # Table Headers
        lbl_kw = {"font": ctk.CTkFont(weight="bold", size=12), "text_color": "gray50"}
        ctk.CTkLabel(self.table_frame, text="Folder Name", **lbl_kw).grid(row=0, column=0, padx=(5,10), pady=10, sticky="w")
        ctk.CTkLabel(self.table_frame, text="Max Width (px)", **lbl_kw).grid(row=0, column=1, padx=10, pady=10, sticky="w")
        ctk.CTkLabel(self.table_frame, text="Max Height (px)", **lbl_kw).grid(row=0, column=2, padx=10, pady=10, sticky="w")
        ctk.CTkLabel(self.table_frame, text="Target (KB)", **lbl_kw).grid(row=0, column=3, padx=10, pady=10, sticky="w")

        # Load Defaults
        default_specs = [
            ("hero-main", 1400, 1960, 400), ("hero-float", 700, 980, 180),
            ("product", 1200, 1200, 300), ("about-main", 1200, 1600, 350),
            ("category", 400, 400, 80)
        ]
        for name, w, h, kb in default_specs:
            self.add_section_row(name, w, h, kb)

        # --- Card 3: Execution ---
        card_exec = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_exec.grid(row=2, column=0, pady=(0, 20), sticky="ew")
        card_exec.grid_columnconfigure(1, weight=1)

        self.batch_mode_var = ctk.StringVar(value="crop")
        
        ctk.CTkRadioButton(card_exec, text="Crop & Resize (Strict adherence to dimensions)", variable=self.batch_mode_var, value="crop", font=self.font_body).grid(row=0, column=0, padx=25, pady=(25, 10), sticky="w")
        ctk.CTkRadioButton(card_exec, text="Compress Only (Preserves original aspect ratio)", variable=self.batch_mode_var, value="compress", font=self.font_body).grid(row=1, column=0, padx=25, pady=(0, 25), sticky="w")

        self.btn_run_batch = ctk.CTkButton(card_exec, text="IGNITE PIPELINE", font=self.font_h1, fg_color=self.success_color, hover_color="#1B5E20", height=60, corner_radius=8, command=self.start_batch_thread)
        self.btn_run_batch.grid(row=0, column=1, rowspan=2, padx=25, pady=25, sticky="ew")

        self.batch_progress = ctk.CTkProgressBar(scroll_container, height=6, progress_color=self.success_color)
        self.batch_progress.grid(row=3, column=0, pady=(0, 20), sticky="ew")
        self.batch_progress.set(0)

    # =========================================================
    # VIEW: CUSTOM FILES
    # =========================================================
    def setup_custom_view(self):
        # Header
        ctk.CTkLabel(self.frame_custom, text="Custom File Optimization", font=self.font_logo).grid(row=0, column=0, padx=30, pady=(30, 20), sticky="w")

        scroll_container = ctk.CTkScrollableFrame(self.frame_custom, fg_color="transparent")
        scroll_container.grid(row=1, column=0, sticky="nsew", padx=15)
        scroll_container.grid_columnconfigure(0, weight=1)

        # --- Card 1: Data ---
        card_io = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_io.grid(row=0, column=0, pady=(0, 20), sticky="ew")
        card_io.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_io, text="Source & Destination", font=self.font_h2).grid(row=0, column=0, columnspan=3, padx=25, pady=(25, 15), sticky="w")

        ctk.CTkLabel(card_io, text="Source Files:", font=self.font_body, text_color="gray70").grid(row=1, column=0, padx=25, pady=10, sticky="w")
        self.entry_files = ctk.CTkEntry(card_io, height=35)
        self.entry_files.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        ctk.CTkButton(card_io, text="Browse", width=80, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=self.browse_multiple_files).grid(row=1, column=2, padx=(0, 25), pady=10)

        ctk.CTkLabel(card_io, text="Output Folder:", font=self.font_body, text_color="gray70").grid(row=2, column=0, padx=25, pady=(0, 25), sticky="w")
        self.entry_out_dir_custom = ctk.CTkEntry(card_io, height=35)
        self.entry_out_dir_custom.grid(row=2, column=1, padx=(0, 10), pady=(0, 25), sticky="ew")
        ctk.CTkButton(card_io, text="Browse", width=80, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_directory(self.entry_out_dir_custom)).grid(row=2, column=2, padx=(0, 25), pady=(0, 25))

        # --- Card 2: Settings ---
        card_settings = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_settings.grid(row=1, column=0, pady=(0, 20), sticky="ew")
        card_settings.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_settings, text="Quality Parameters", font=self.font_h2).grid(row=0, column=0, columnspan=3, padx=25, pady=(25, 15), sticky="w")

        ctk.CTkLabel(card_settings, text="Target Size (KB):", font=self.font_body, text_color="gray70").grid(row=1, column=0, padx=25, pady=(0, 25), sticky="w")
        self.entry_size = ctk.CTkEntry(card_settings, height=35, placeholder_text="Leave blank for smart auto-optimization")
        self.entry_size.grid(row=1, column=1, columnspan=2, padx=(0, 25), pady=(0, 25), sticky="ew")

        # --- Execution ---
        self.btn_run_custom = ctk.CTkButton(scroll_container, text="PROCESS SELECTED FILES", font=self.font_h1, fg_color=self.success_color, hover_color="#1B5E20", height=60, corner_radius=8, command=self.start_custom_thread)
        self.btn_run_custom.grid(row=2, column=0, pady=(10, 20), sticky="ew")

# =========================================================
    # VIEW: FORMAT CONVERTER
    # =========================================================
    def setup_converter_view(self):
        ctk.CTkLabel(self.frame_converter, text="Universal Format Converter", font=self.font_logo).grid(row=0, column=0, padx=30, pady=(30, 20), sticky="w")

        scroll_container = ctk.CTkScrollableFrame(self.frame_converter, fg_color="transparent")
        scroll_container.grid(row=1, column=0, sticky="nsew", padx=15)
        scroll_container.grid_columnconfigure(0, weight=1)

        # --- Card: Converter Settings ---
        card_conv = ctk.CTkFrame(scroll_container, fg_color=self.card_color, corner_radius=12)
        card_conv.grid(row=0, column=0, pady=(0, 20), sticky="ew")
        card_conv.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card_conv, text="File Targeting", font=self.font_h2).grid(row=0, column=0, columnspan=3, padx=25, pady=(25, 15), sticky="w")

        # Inputs
        ctk.CTkLabel(card_conv, text="Source Image(s):", font=self.font_body, text_color="gray70").grid(row=1, column=0, padx=25, pady=10, sticky="w")
        self.entry_conv_in = ctk.CTkEntry(card_conv, height=35)
        self.entry_conv_in.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        
        btn_frame = ctk.CTkFrame(card_conv, fg_color="transparent")
        btn_frame.grid(row=1, column=2, padx=(0, 25), pady=10)
        ctk.CTkButton(btn_frame, text="Files", width=60, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_multiple_files_target(self.entry_conv_in)).pack(side="left", padx=(0,5))
        ctk.CTkButton(btn_frame, text="Folder", width=60, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_directory(self.entry_conv_in)).pack(side="left")

        # Outputs
        ctk.CTkLabel(card_conv, text="Output Directory:", font=self.font_body, text_color="gray70").grid(row=2, column=0, padx=25, pady=(0, 10), sticky="w")
        self.entry_conv_out = ctk.CTkEntry(card_conv, height=35)
        self.entry_conv_out.grid(row=2, column=1, padx=(0, 10), pady=(0, 10), sticky="ew")
        ctk.CTkButton(card_conv, text="Browse", width=125, height=35, fg_color="transparent", border_width=1, border_color="gray40", command=lambda: self.browse_directory(self.entry_conv_out)).grid(row=2, column=2, padx=(0, 25), pady=(0, 10))

        # Format Dropdown
        ctk.CTkLabel(card_conv, text="Target Format:", font=self.font_body, text_color="gray70").grid(row=3, column=0, padx=25, pady=(15, 25), sticky="w")
        self.conv_format_var = ctk.StringVar(value="PNG")
        self.conv_dropdown = ctk.CTkOptionMenu(card_conv, variable=self.conv_format_var, values=["PNG", "JPEG", "WEBP", "TIFF", "BMP", "ICO"], height=35)
        self.conv_dropdown.grid(row=3, column=1, sticky="w", pady=(15, 25))

        # --- Execution ---
        self.btn_run_conv = ctk.CTkButton(scroll_container, text="START CONVERSION", font=self.font_h1, fg_color=self.accent_color, hover_color="#2980b9", height=60, corner_radius=8, command=self.start_converter_thread)
        self.btn_run_conv.grid(row=1, column=0, pady=(10, 20), sticky="ew")

    def browse_multiple_files_target(self, entry_widget):
        """Helper to dump multiple files into a specific entry."""
        file_paths = filedialog.askopenfilenames(filetypes=[("Image Files", "*.tiff *.tif *.jpg *.jpeg *.png *.webp *.bmp *.ico")])
        if file_paths:
            entry_widget.delete(0, 'end')
            entry_widget.insert(0, "; ".join(file_paths))


    # =========================================================
    # VIEW: GUIDE
    # =========================================================
    def setup_guide_view(self):
        ctk.CTkLabel(self.frame_guide, text="Documentation", font=self.font_logo).grid(row=0, column=0, padx=30, pady=(30, 20), sticky="w")

        card_guide = ctk.CTkFrame(self.frame_guide, fg_color=self.card_color, corner_radius=12)
        card_guide.grid(row=1, column=0, padx=30, pady=(0, 30), sticky="nsew")
        card_guide.grid_columnconfigure(0, weight=1)
        card_guide.grid_rowconfigure(0, weight=1)

        guide_text = """
System Architecture & Pipeline Protocol
========================================================

BATCH PROCESS PIPELINE
Designed to process entire folders of images at once, sorting them into categories with strict rules.

1. Workspace: Select an empty "Raw Input Directory".
2. Rules: Define your target sizes and max dimensions.
3. Generator: Click "Generate Folders". This builds empty folders matching your rules.
4. Drop Files: Open your OS file explorer and drop raw images (TIFF, PNG, JPG) into those folders.
5. Execution: Select an "Output Directory" and Ignite the Pipeline.
   - Crop & Resize: Forces the exact dimensions (cuts off edges if needed).
   - Compress Only: Preserves original aspect ratio.

CUSTOM FILES MODE
Perfect for quick, one-off optimizations without setting up folders.

1. Select one or multiple files across any directory.
2. Define a target KB size. If left blank, the system uses Smart Auto-Optimize.

CORE TECHNOLOGY
- Fully Multi-Threaded: Utilizes all CPU cores automatically.
- High-Performance Buffer: Large formats (200MB+ TIFFs) are processed in RAM via binary search compression to hit exact target sizes.
        """
        textbox = ctk.CTkTextbox(card_guide, font=self.font_body, fg_color="transparent", text_color="gray80", wrap="word")
        textbox.grid(row=0, column=0, padx=30, pady=30, sticky="nsew")
        textbox.insert("0.0", guide_text.strip())
        textbox.configure(state="disabled")

    # =========================================================
    # GLOBAL TERMINAL CONSOLE
    # =========================================================
    def setup_global_console(self):
        console_frame = ctk.CTkFrame(self, fg_color=self.sidebar_color, corner_radius=0)
        console_frame.grid(row=1, column=1, sticky="ew") # Attached to bottom of main content area
        console_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(console_frame, fg_color="transparent", height=24)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(5,0))
        ctk.CTkLabel(header, text=">_ SYSTEM TERMINAL", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="gray50").place(relx=0, rely=0.5, anchor="w")

        self.console = ctk.CTkTextbox(console_frame, height=140, state="disabled", font=self.font_mono, text_color="#A9B7C6", fg_color="transparent", border_width=0)
        self.console.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

    # =========================================================
    # HELPER FUNCTIONS
    # =========================================================
    def browse_directory(self, entry_widget):
        dir_path = filedialog.askdirectory()
        if dir_path:
            entry_widget.delete(0, 'end')
            entry_widget.insert(0, dir_path)

    def browse_multiple_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Image Files", "*.tiff *.tif *.jpg *.jpeg *.png *.webp")])
        if file_paths:
            self.entry_files.delete(0, 'end')
            self.entry_files.insert(0, "; ".join(file_paths))

    def log(self, message):
        self.console.configure(state="normal")
        self.console.insert("end", message + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def add_section_row(self, name="", w="", h="", kb=""):
        idx = self.current_grid_row
        
        entry_args = {"height": 30, "fg_color": self.sidebar_color, "border_width": 0}
        
        e_name = ctk.CTkEntry(self.table_frame, **entry_args)
        e_name.grid(row=idx, column=0, padx=(5,10), pady=4, sticky="ew")
        e_name.insert(0, str(name))

        e_w = ctk.CTkEntry(self.table_frame, **entry_args)
        e_w.grid(row=idx, column=1, padx=10, pady=4, sticky="ew")
        e_w.insert(0, str(w))

        e_h = ctk.CTkEntry(self.table_frame, **entry_args)
        e_h.grid(row=idx, column=2, padx=10, pady=4, sticky="ew")
        e_h.insert(0, str(h))

        e_kb = ctk.CTkEntry(self.table_frame, **entry_args)
        e_kb.grid(row=idx, column=3, padx=10, pady=4, sticky="ew")
        e_kb.insert(0, str(kb))

        btn_del = ctk.CTkButton(self.table_frame, text="✕", width=30, height=30, fg_color="transparent", text_color="gray50", hover_color=self.danger_color)
        btn_del.grid(row=idx, column=4, padx=(10,5), pady=4)

        row_data = {"name": e_name, "w": e_w, "h": e_h, "kb": e_kb, "btn": btn_del}
        self.section_rows.append(row_data)

        btn_del.configure(command=lambda r=row_data: self.remove_section_row(r))
        self.current_grid_row += 1

    def remove_section_row(self, row_data):
        for key in ["name", "w", "h", "kb", "btn"]:
            row_data[key].destroy()
        self.section_rows.remove(row_data)

    def get_dynamic_sections(self):
        sections = {}
        DEFAULT_KB = 500.0  # Set your preferred default target size here

        for r in self.section_rows:
            name = r["name"].get().strip()
            if not name: continue
            
            w_str = r["w"].get().strip()
            h_str = r["h"].get().strip()
            kb_str = r["kb"].get().strip()

            try:
                # If the field has a value, parse it. If empty, use None or the default.
                w = int(w_str) if w_str else None
                h = int(h_str) if h_str else None
                kb = float(kb_str) if kb_str else DEFAULT_KB
                
                sections[name] = (w, h, kb)
            except ValueError:
                self.log(f"⚠️ Ignored rule '{name}' - Dimensions/KB must be valid numbers if provided.")
        return sections

    def create_folder_structure(self):
        in_dir = self.entry_batch_in.get().strip()
        if not in_dir:
            self.log("❌ Setup Error: Select a Raw Input Directory first.")
            return

        sections = self.get_dynamic_sections()
        if not sections:
            self.log("❌ Setup Error: No valid optimization rules found.")
            return

        base_path = Path(in_dir)
        created = 0
        for name in sections.keys():
            cat_path = base_path / name
            if not cat_path.exists():
                cat_path.mkdir(parents=True, exist_ok=True)
                created += 1
        
        self.log(f"📁 Verified {len(sections)} architecture folders in {base_path.name}. (Newly created: {created})")

    # =========================================================
    # EXECUTORS & BACKGROUND TASKS
    # =========================================================
    def start_batch_thread(self):
        in_dir = self.entry_batch_in.get().strip()
        out_dir = self.entry_batch_out.get().strip()

        if not in_dir or not out_dir:
            self.log("❌ Pipeline Error: Input and Output directories are required.")
            return

        sections = self.get_dynamic_sections()
        if not sections: return

        self.btn_run_batch.configure(state="disabled", text="PROCESSING...", fg_color=self.accent_color)
        self.batch_progress.set(0)
        self.log("\n[SYSTEM] Initializing Batch Pipeline...")
        
        threading.Thread(target=self.run_batch_logic, args=(Path(in_dir), Path(out_dir), sections), daemon=True).start()

    def start_custom_thread(self):
        files_str = self.entry_files.get().strip()
        out_dir_str = self.entry_out_dir_custom.get().strip()
        target_kb_str = self.entry_size.get().strip()

        if not files_str or not out_dir_str:
            self.log("❌ Pipeline Error: Source files and Output folder are required.")
            return

        file_paths = [Path(p.strip()) for p in files_str.split(";") if p.strip()]
        valid_files = [p for p in file_paths if p.exists() and p.is_file()]

        if not valid_files:
            self.log("❌ Pipeline Error: No valid files found at specified paths.")
            return

        self.btn_run_custom.configure(state="disabled", text="PROCESSING...", fg_color=self.accent_color)
        self.log(f"\n[SYSTEM] Initializing Custom Pipeline for {len(valid_files)} files...")
        
        threading.Thread(target=self.run_custom_logic, args=(valid_files, out_dir_str, target_kb_str), daemon=True).start()


    def start_converter_thread(self):
            in_path_str = self.entry_conv_in.get().strip()
            out_dir_str = self.entry_conv_out.get().strip()
            target_fmt = self.conv_format_var.get()

            if not in_path_str or not out_dir_str:
                self.log("❌ Converter Error: Source path and Output directory are required.")
                return

            self.btn_run_conv.configure(state="disabled", text="CONVERTING...", fg_color="gray")
            self.log(f"\n[SYSTEM] Initializing Format Conversion Engine to format: {target_fmt}...")
            
            threading.Thread(target=self.run_converter_logic, args=(in_path_str, out_dir_str, target_fmt), daemon=True).start()

    def run_converter_logic(self, in_path_str, out_dir_str, target_fmt):
        out_dir = Path(out_dir_str)
        out_dir.mkdir(parents=True, exist_ok=True)

        files_to_process = []
        
        # Check if the input is a single directory or a semicolon-separated list of files
        if ";" not in in_path_str and Path(in_path_str).is_dir():
            valid_exts = {".tiff", ".tif", ".jpg", ".jpeg", ".png", ".webp", ".bmp"}
            files_to_process = [p for p in Path(in_path_str).iterdir() if p.suffix.lower() in valid_exts]
        else:
            files_to_process = [Path(p.strip()) for p in in_path_str.split(";") if p.strip() and Path(p.strip()).is_file()]

        if not files_to_process:
            self.log("❌ Converter Error: No valid image files found.")
            self.after(0, lambda: self.btn_run_conv.configure(state="normal", text="START CONVERSION", fg_color=self.accent_color))
            return

        for file_path in files_to_process:
            try:
                with Image.open(file_path) as img:
                    output_name = f"{file_path.stem}.{target_fmt.lower()}"
                    output_path = out_dir / output_name

                    # Handle Alpha Channel issues (JPEG and BMP don't support transparency)
                    if target_fmt in ["JPEG", "BMP"] and img.mode in ("RGBA", "P"):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'RGBA':
                            bg.paste(img, mask=img.split()[3])
                        else:
                            bg.paste(img)
                        img = bg
                    
                    if target_fmt == "JPEG":
                        img.save(output_path, target_fmt, quality=100, subsampling=0)
                    elif target_fmt == "WEBP":
                        img.save(output_path, target_fmt, quality=100, lossless=True)
                    else:
                        img.save(output_path, target_fmt)

                self.log(f"🔄 Converted: {file_path.name} -> {output_name}")
            except Exception as e:
                self.log(f"❌ Error converting {file_path.name}: {e}")

        self.log("\n[SUCCESS] Format Conversion Batch Complete.")
        self.after(0, lambda: self.btn_run_conv.configure(state="normal", text="START CONVERSION", fg_color=self.accent_color))


    def run_batch_logic(self, input_root, output_root, sections):
        crop_enabled = (self.batch_mode_var.get() == "crop")
        jobs = []

        for section_name, (width, height, max_kb) in sections.items():
            source_dir = input_root / section_name
            target_dir = output_root / section_name
            if not source_dir.exists(): continue
            
            files_found = [f for f in source_dir.iterdir() if f.suffix.lower() in VALID_EXTENSIONS]
            if files_found:
                target_dir.mkdir(parents=True, exist_ok=True)
                for file_path in files_found:
                    jobs.append((file_path, target_dir, width, height, max_kb, crop_enabled))
        
        if not jobs:
            self.log("⚠️ Pipeline Warning: No valid images found in the rule-defined subdirectories.")
            self.after(0, lambda: self.btn_run_batch.configure(state="normal", text="IGNITE PIPELINE", fg_color=self.success_color))
            return

        self.log(f"-> Acquired {len(jobs)} targets. Dispatching to CPU cores...")
        total_orig, total_final, completed = 0, 0, 0

        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [executor.submit(process_single_image_task, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                success, orig_size, final_size, msg = future.result()
                self.log(msg)
                if success:
                    total_orig += orig_size
                    total_final += final_size
                completed += 1
                self.after(0, self.batch_progress.set, completed / len(jobs))

        saved_mb = (total_orig - total_final) / (1024 * 1024)
        self.log(f"\n[SUCCESS] Batch Completed. Reclaimed Data: {saved_mb:.2f} MB")
        self.after(0, lambda: self.btn_run_batch.configure(state="normal", text="IGNITE PIPELINE", fg_color=self.success_color))

    def run_custom_logic(self, file_paths, output_dir_str, target_kb_str):
        output_dir = Path(output_dir_str)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        target_kb = None
        if target_kb_str:
            try: target_kb = float(target_kb_str)
            except ValueError: self.log("⚠️ Parameter Warning: Invalid KB target. Defaulting to Auto (Q:80).")

        total_orig, total_final = 0, 0

        for file_path in file_paths:
            output_path = output_dir / f"{file_path.stem}_optimized.webp"
            try:
                original_size = file_path.stat().st_size
                with Image.open(file_path) as img:
                    if img.mode == 'RGBA':
                        bg = Image.new('RGBA', img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[3])
                        img = bg.convert('RGB')
                    elif img.mode != 'RGB': img = img.convert('RGB')
                        
                    if target_kb: final_quality = save_closest_to_target_size(img, output_path, target_kb, "WEBP")
                    else:
                        img.save(output_path, format="WEBP", quality=80, method=6)
                        final_quality = 80
                        
                final_size = output_path.stat().st_size
                total_orig += original_size
                total_final += final_size
                self.log(f"✅ {file_path.name} -> {final_size / 1024:.2f} KB (Q: {final_quality}%)")
            except Exception as e:
                self.log(f"❌ Failed to process {file_path.name}: {e}")

        saved_mb = (total_orig - total_final) / (1024 * 1024)
        self.log(f"\n[SUCCESS] Custom Batch Completed. Reclaimed Data: {saved_mb:.2f} MB")
        self.after(0, lambda: self.btn_run_custom.configure(state="normal", text="PROCESS SELECTED FILES", fg_color=self.success_color))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = ArtOptimizerApp()
    app.mainloop()