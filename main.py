import os
import io
from pathlib import Path
from PIL import Image, ImageOps
import concurrent.futures
from tqdm import tqdm

# CRITICAL: Allow Pillow to open massive 200MB TIFFs
Image.MAX_IMAGE_PIXELS = None

# Specifications matching your guide
# Format: "directory_name": (max_width, max_height, target_size_kb)
SECTIONS = {
    "hero-main": (1400, 1960, 400),
    "hero-float": (700, 980, 180),
    "product": (1200, 1200, 300),
    "about-main": (1200, 1600, 350),
    "about-float": (800, 1100, 200),
    "category": (400, 400, 80),
    "course": (800, 450, 150),
    "testimonial": (200, 200, 40),
    "catalog": (1200, 1200, 300),
}

INPUT_ROOT = Path("./raw_images")
OUTPUT_ROOT = Path("./optimized_images")

def get_user_mode():
    print("================================================")
    print("   Ultimate Art Optimization Pipeline           ")
    print("================================================")
    print("[1] Crop & Resize (Strict guide dimensions) - BATCH")
    print("[2] Compress Only (Preserve original artwork) - BATCH")
    print("[3] Custom Single File (Target size or Auto)\n")
    
    while True:
        choice = input("Enter choice (1, 2, or 3): ").strip()
        if choice in ['1', '2', '3']:
            return choice
        print("Invalid input.")

def save_closest_to_target_size(img, output_path, target_kb, image_format="WEBP"):
    """
    Uses binary search in RAM to find the absolute highest visual quality 
    that fits just under the target_kb limit.
    """
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

def process_single_image(args):
    """
    Isolated worker function handling a single image so it can 
    run on its own CPU core.
    """
    file_path, target_dir, width, height, max_kb, crop_enabled = args
    output_path = target_dir / f"{file_path.stem}.webp"
    
    try:
        original_size = file_path.stat().st_size
        
        with Image.open(file_path) as img:
            # 1. Colorspace cleanup
            if img.mode == 'RGBA':
                background = Image.new('RGBA', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # 2. Dimensions logic
            if crop_enabled:
                optimized_img = ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            else:
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                optimized_img = img
            
            # 3. Target size binary search compression
            final_quality = save_closest_to_target_size(optimized_img, output_path, max_kb, "WEBP")
                
        final_size = output_path.stat().st_size
        return True, original_size, final_size, f"{file_path.name} (Q: {final_quality}%)"

    except Exception as e:
        return False, 0, 0, f"{file_path.name} (Error: {e})"

def handle_custom_file():
    """
    Handles a single custom file input by the user, allowing for 
    specific target sizes or auto-compression.
    """
    print("\n--- Custom Single File Mode ---")
    file_path_str = input("Enter the full path to the image file: ").strip()
    
    # Strip quotes in case the user dragged and dropped the file into the terminal
    file_path_str = file_path_str.strip('"').strip("'")
    file_path = Path(file_path_str)
    
    if not file_path.exists() or not file_path.is_file():
        print(f"Error: File not found at {file_path}")
        return
        
    target_kb_str = input("Enter target size in KB (or press Enter for auto best-compression): ").strip()
    if target_kb_str:
        try:
            target_kb = float(target_kb_str)
        except ValueError:
            print("Invalid number entered. Defaulting to auto compression.")
            target_kb = None
    else:
        target_kb = None

    # Output to an 'optimized' folder in the same directory as the source image
    output_dir = file_path.parent / "optimized"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{file_path.stem}_optimized.webp"
    
    print(f"\nProcessing {file_path.name}...")
    
    try:
        original_size = file_path.stat().st_size
        with Image.open(file_path) as img:
            # Colorspace cleanup
            if img.mode == 'RGBA':
                background = Image.new('RGBA', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
                
            if target_kb:
                # Binary search for exact size
                final_quality = save_closest_to_target_size(img, output_path, target_kb, "WEBP")
            else:
                # Auto best-compression (Default WebP at Q:80 is a great sweet spot)
                img.save(output_path, format="WEBP", quality=80, method=6)
                final_quality = 80
                
        final_size = output_path.stat().st_size
        
        print("\n================================================")
        print("               FILE COMPLETE                    ")
        print("================================================")
        print(f"Saved to:      {output_path}")
        print(f"Original Size: {original_size / 1024:.2f} KB")
        print(f"Final Size:    {final_size / 1024:.2f} KB")
        print(f"Quality used:  {final_quality}%")
        
    except Exception as e:
        print(f"Failed to process image: {e}")

def main():
    mode = get_user_mode()
    
    # Route to single file mode
    if mode == '3':
        handle_custom_file()
        return

    # Route to batch processing
    crop_enabled = (mode == '1')
    print("\nScanning directories...")
    
    jobs = []
    valid_extensions = {".tiff", ".tif", ".jpg", ".jpeg", ".png"}
    
    for section, (width, height, max_kb) in SECTIONS.items():
        source_dir = INPUT_ROOT / section
        target_dir = OUTPUT_ROOT / section
        
        if not source_dir.exists():
            source_dir.mkdir(parents=True, exist_ok=True)
            continue
            
        target_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path in source_dir.iterdir():
            if file_path.suffix.lower() in valid_extensions:
                jobs.append((file_path, target_dir, width, height, max_kb, crop_enabled))
    
    if not jobs:
        print("No images found in ./raw_images subdirectories.")
        print("Please drop your TIFF/JPG files into the generated folders and run again.")
        return

    print(f"Found {len(jobs)} images. Igniting multi-core processing...\n")
    
    total_original_bytes = 0
    total_final_bytes = 0
    failures = []

    # Execute jobs using all available CPU cores
    with concurrent.futures.ProcessPoolExecutor() as executor:
        results = list(tqdm(executor.map(process_single_image, jobs), total=len(jobs), desc="Compressing"))

    # Tally results
    for success, orig_size, final_size, msg in results:
        if success:
            total_original_bytes += orig_size
            total_final_bytes += final_size
        else:
            failures.append(msg)

    # Print Final Report
    orig_mb = total_original_bytes / (1024 * 1024)
    final_mb = total_final_bytes / (1024 * 1024)
    saved_mb = orig_mb - final_mb
    
    print("\n================================================")
    print("                 BATCH COMPLETE                 ")
    print("================================================")
    print(f"Original Archive Size:  {orig_mb:.2f} MB")
    print(f"Final Web-Ready Size:   {final_mb:.2f} MB")
    print(f"Total Disk Space Saved: {saved_mb:.2f} MB")
    
    if failures:
        print("\nFailed to process (usually due to corrupt source files):")
        for f in failures:
            print(f" - {f}")

if __name__ == "__main__":
    main()