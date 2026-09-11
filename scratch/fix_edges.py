import sys
from PIL import Image

def process_image(input_path, output_path):
    img = Image.open(input_path).convert("RGBA")
    data = img.getdata()
    new_data = []
    
    for item in data:
        r, g, b, a = item
        # If the pixel is mostly white/gray and semi-transparent, it's a fringe
        if a == 0:
            new_data.append((0, 0, 0, 0))
        else:
            # White fringe is usually high RGB values and maybe less than 255 alpha, or even 255 alpha if it's just a white outline.
            # Let's remove light pixels that are near the transparent edge.
            # Actually, a simpler way is: if r>200, g>200, b>200 and a<255, make it transparent
            if r > 200 and g > 200 and b > 200 and a < 255:
                new_data.append((0, 0, 0, 0))
            elif r > 230 and g > 230 and b > 230:
                new_data.append((0, 0, 0, 0))
            else:
                new_data.append(item)
                
    img.putdata(new_data)
    img.save(output_path, "PNG")

process_image('assets/tabby_cat_spritesheet.png', 'assets/tabby_cat_spritesheet_fixed.png')
