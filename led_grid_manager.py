import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
import json
import os
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict, field
import math


@dataclass
class LEDGrouping:
    """Represents a single LED grid grouping"""
    name: str
    x: int = 10
    y: int = 10
    row_modules: int = 1  # Number of 8x8 modules vertically
    col_modules: int = 1  # Number of 8x8 modules horizontally
    round_leds: bool = False  # True for round, False for square
    ref_char: str = ""  # Reference character for bytecode (auto-generated from name)
    led_color: str = "#f00"
    use_custom_color: bool = False
    # Optional per-LED colors. If None, file predates color support and default color applies.
    led_colors: Optional[List[List[Optional[str]]]] = None
    leds: List[List[int]] = field(default_factory=lambda: [[0 for _ in range(8)] for _ in range(8)])
    
    @property
    def rows(self) -> int:
        return self.row_modules * 8
    
    @property
    def cols(self) -> int:
        return self.col_modules * 8
    
    def __post_init__(self):
        # Auto-generate ref_char from name if not set
        if not self.ref_char and self.name:
            # Get first letter, skip numbers
            for char in self.name:
                if char.isalpha():
                    self.ref_char = char.upper()
                    break
            if not self.ref_char:
                self.ref_char = "X"
        
        # Ensure LED array is properly sized
        if not self.leds or len(self.leds) != self.rows:
            self.leds = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        else:
            # Resize existing LED array if dimensions changed
            for row in self.leds:
                while len(row) < self.cols:
                    row.append(0)
                while len(row) > self.cols:
                    row.pop()

        # Ensure led_colors shape matches leds if provided; keep None to indicate older files
        if self.led_colors is None:
            # leave as None to signal legacy files (default color applies)
            pass
        else:
            # normalize size: copy existing values where possible, fill missing with None
            new_colors = [[None for _ in range(self.cols)] for _ in range(self.rows)]
            for r in range(min(len(self.led_colors), self.rows)):
                row_colors = self.led_colors[r] or []
                for c in range(min(len(row_colors), self.cols)):
                    new_colors[r][c] = row_colors[c]
            self.led_colors = new_colors


class LEDGridManager:
    def __init__(self, root):
        self.root = root
        self.root.title("LED Grid Manager")
        self.root.geometry("1200x700")
        
        self.groupings: List[LEDGrouping] = []
        self.selected_grouping: LEDGrouping = None
        self.dragging_grouping: LEDGrouping = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        # Canvas panning state (world offset in pixels)
        self.view_offset = [0, 0]
        self.panning = False
        self.pan_start = (0, 0)
        # Zoom state (world units -> screen scale)
        self.view_scale = 1.0
        self.min_scale = 0.2
        self.max_scale = 4.0
        
        self.led_size = 15  # Size of each LED square in pixels (75% of 20)
        self.led_gap = 2    # Gap between LEDs
        self.module_gap = 4  # Gap between 8x8 modules (1/4 of led_size)
        
        # Icon storage
        self.icons: Dict[str, Optional[tk.PhotoImage]] = {}
        # Theme colors using Material Design 3 tokens
        self.theme = "dark"
        self.default_led_color = "#f00"
        self.colors = {
            "light": {
                "surface": "#FFFBFE",
                "surface_variant": "#E7E0EC",
                "background": "#FFFBFE",
                "primary": "#6750A4",
                "on_primary": "#FFFFFF",
                "on_surface": "#1C1B1F",
                "on_surface_variant": "#49454F",
                "outline": "#79747E",
                "outline_variant": "#CFC7D1",
                "secondary": "#625B71",
                "surface_tint": "#6750A4"
            },
            "dark": {
                "surface": "#1C1B1F",
                "surface_variant": "#49454F",
                "background": "#1C1B1F",
                "primary": "#D0BCFF",
                "on_primary": "#381E72",
                "on_surface": "#E6E1E5",
                "on_surface_variant": "#E6E1E5",
                "outline": "#938F99",
                "outline_variant": "#625B71",
                "secondary": "#CCC2DC",
                "surface_tint": "#CCC2DC"
            }
        }
        # Create UI
        self.create_widgets()
        self.load_project()
        
    def create_widgets(self):
        """Create the UI layout"""
        # Top control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        left_frame = ttk.Frame(control_frame)
        left_frame.pack(side=tk.LEFT)
        right_frame = ttk.Frame(control_frame)
        right_frame.pack(side=tk.RIGHT)

        # Load icons
        self.load_icons()

        # Toolbar buttons (left side)
        ttk.Button(left_frame, image=self.icons.get('new'), text=" New", compound=tk.LEFT, command=self.add_grouping).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_frame, image=self.icons.get('save'), text=" Save", compound=tk.LEFT, command=self.save_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_frame, image=self.icons.get('load'), text=" Load", compound=tk.LEFT, command=self.load_project_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_frame, image=self.icons.get('publish'), text=" Publish", compound=tk.LEFT, command=self.export_code).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_frame, image=self.icons.get('clear'), text=" Clear All", compound=tk.LEFT, command=self.clear_all).pack(side=tk.LEFT, padx=2)

        # Canvas for LED display
        self.canvas = tk.Canvas(self.root, bg="white", cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        # Middle-button (Button-2) pan bindings
        self.canvas.bind("<Button-2>", self.on_canvas_middle_press)
        self.canvas.bind("<B2-Motion>", self.on_canvas_middle_motion)
        self.canvas.bind("<ButtonRelease-2>", self.on_canvas_middle_release)
        # Mouse wheel zoom (Windows/Linux compatibility)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        # Double middle click to auto-fit
        self.canvas.bind("<Double-Button-2>", self.on_double_middle)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        
        # Create context menu (icons will be added if available)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Edit Properties", command=self.show_properties_dialog, image=self.icons.get('edit'), compound=tk.LEFT)
        self.context_menu.add_command(label="Duplicate", command=self.duplicate_grouping, image=self.icons.get('duplicate'), compound=tk.LEFT)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.remove_grouping, image=self.icons.get('delete'), compound=tk.LEFT)
        self.context_menu.add_command(label="Toggle LED Shape", command=self.toggle_led_shape_quick, image=self.icons.get('shape'), compound=tk.LEFT)

        # LED color default button + theme toggle on right side
        self.default_color_btn = ttk.Button(right_frame, text="LED Color", command=self.pick_default_led_color)
        self.default_color_btn.pack(side=tk.RIGHT, padx=2)
        self.theme_btn = ttk.Button(right_frame, image=self.icons.get('light'), command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=2)
        self.apply_theme()
        
    def add_grouping(self):
        """Add a new LED grouping"""
        name = f"LED_{len(self.groupings)}"
        grouping = LEDGrouping(name=name, x=20 + len(self.groupings) * 30, y=20 + len(self.groupings) * 30)
        self.groupings.append(grouping)
        self.refresh_display()
        
    def remove_grouping(self):
        """Remove the selected grouping"""
        if self.selected_grouping and self.selected_grouping in self.groupings:
            self.groupings.remove(self.selected_grouping)
            self.selected_grouping = None
            self.refresh_display()
            
    def clear_all(self):
        """Clear all groupings"""
        if messagebox.askyesno("Confirm", "Clear all groupings?"):
            self.groupings.clear()
            self.selected_grouping = None
            self.refresh_display()
            
    def on_grouping_select(self, event):
        """Handle grouping selection from listbox"""
        pass  # No longer needed
            
    def on_canvas_click(self, event):
        """Handle canvas click - toggle LED or select grouping"""
        # Convert to world coords and check groupings from top (end of list) to bottom
        wx, wy = self.screen_to_world(event.x, event.y)
        clicked_grouping = None
        for grouping in reversed(self.groupings):
            clicked_grouping = self.find_grouping_at_in_list(grouping, wx, wy)
            if clicked_grouping:
                break
        
        if clicked_grouping:
            # Check if clicked on LED
            row, col = self.find_led_at(clicked_grouping, wx, wy)
            if row is not None and col is not None:
                # Toggle LED
                clicked_grouping.leds[row][col] = 1 - clicked_grouping.leds[row][col]
                self.refresh_display()
            else:
                # Clicked on grouping header area - prepare to drag
                # Bring grouping to front by moving to end of list
                if clicked_grouping in self.groupings:
                    self.groupings.remove(clicked_grouping)
                    self.groupings.append(clicked_grouping)
                
                self.dragging_grouping = clicked_grouping
                self.drag_offset = (wx - clicked_grouping.x, wy - clicked_grouping.y)
                self.selected_grouping = clicked_grouping
                self.refresh_display()
        
    def on_canvas_drag(self, event):
        """Handle canvas drag"""
        if self.dragging_grouping:
            wx, wy = self.screen_to_world(event.x, event.y)
            self.dragging_grouping.x = wx - self.drag_offset[0]
            self.dragging_grouping.y = wy - self.drag_offset[1]
            self.refresh_display()
            
    def on_canvas_release(self, event):
        """Handle canvas drag release"""
        self.dragging_grouping = None
        
    def on_canvas_motion(self, event):
        """Update cursor based on hover"""
        wx, wy = self.screen_to_world(event.x, event.y)
        grouping = self.find_grouping_at(wx, wy)
        if grouping:
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="arrow")
    
    def on_canvas_middle_press(self, event):
        """Start panning the canvas with middle mouse button."""
        self.panning = True
        # store starting screen position
        self.pan_start = (event.x, event.y)

    def on_canvas_middle_motion(self, event):
        """Handle panning motion while middle button held."""
        if not self.panning:
            return
        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]
        # update view offset (screen pixels)
        self.view_offset[0] += dx
        self.view_offset[1] += dy
        # reset pan start to current for smooth incremental panning
        self.pan_start = (event.x, event.y)
        self.refresh_display()

    def on_canvas_middle_release(self, event):
        """End panning."""
        self.panning = False

    def on_mouse_wheel(self, event):
        """Zoom in/out centered at the mouse cursor."""
        # Determine mouse position
        sx, sy = event.x, event.y
        # Get wheel direction
        delta = 0
        try:
            # Windows: event.delta is multiple of 120
            delta = event.delta
        except Exception:
            # Linux: event.num == 4 (up) or 5 (down)
            if hasattr(event, 'num') and event.num == 4:
                delta = 120
            else:
                delta = -120

        factor = 1.1 if delta > 0 else 1 / 1.1
        old_scale = self.view_scale
        new_scale = max(self.min_scale, min(self.max_scale, old_scale * factor))
        if new_scale == old_scale:
            return

        # World coordinate under cursor before zoom
        wx, wy = self.screen_to_world(sx, sy)

        # Apply new scale and adjust offset so the world point stays under cursor
        self.view_scale = new_scale
        self.view_offset[0] = sx - wx * self.view_scale
        self.view_offset[1] = sy - wy * self.view_scale
        self.refresh_display()

    def on_double_middle(self, event):
        """Auto-fit all LEDs into view with generous margin on double middle-click."""
        if not self.groupings:
            # reset to defaults
            self.view_scale = 1.0
            self.view_offset = [0, 0]
            self.refresh_display()
            return

        # Compute world bounding box of all groupings
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        for g in self.groupings:
            gx, gy = g.x, g.y
            cols_pixels = g.col_modules * (8 * (self.led_size + self.led_gap)) + (g.col_modules - 1) * self.module_gap
            rows_pixels = g.row_modules * (8 * (self.led_size + self.led_gap)) + (g.row_modules - 1) * self.module_gap
            w = cols_pixels + 10
            h = rows_pixels + 35
            min_x = min(min_x, gx)
            min_y = min(min_y, gy)
            max_x = max(max_x, gx + w)
            max_y = max(max_y, gy + h)

        bbox_w = max_x - min_x
        bbox_h = max_y - min_y
        if bbox_w <= 0 or bbox_h <= 0:
            return

        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())

        margin = 0.8  # generous margin (80% of canvas used for content)
        target_scale = min((canvas_w * margin) / bbox_w, (canvas_h * margin) / bbox_h)
        target_scale = max(self.min_scale, min(self.max_scale, target_scale))

        # center of bounding box
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        # set scale and offset so that center maps to canvas center
        self.view_scale = target_scale
        self.view_offset[0] = canvas_w / 2.0 - cx * self.view_scale
        self.view_offset[1] = canvas_h / 2.0 - cy * self.view_scale
        self.refresh_display()
    
    def on_canvas_right_click(self, event):
        """Handle right-click on canvas"""
        wx, wy = self.screen_to_world(event.x, event.y)
        clicked_grouping = None
        for grouping in reversed(self.groupings):
            clicked_grouping = self.find_grouping_at_in_list(grouping, wx, wy)
            if clicked_grouping:
                break
        
        if clicked_grouping:
            self.selected_grouping = clicked_grouping
            self.context_menu.post(event.x_root, event.y_root)

    def load_icons(self):
        """Load icons from icons/ directory if present."""
        icon_names = {
            'new': ['add.png'],
            'save': ['save.png'],
            'load': ['load.png'],
            'publish': ['export.png'],
            'clear': ['deleteall.png', 'remove.png'],
            'edit': ['properties.png'],
            'duplicate': ['duplicate.png'],
            'delete': ['deletesingle.png', 'remove.png'],
            'remove': ['remove.png'],
            'shape': [],
            'light': ['lightmode.png'],
            'dark': ['darkmode.png']
        }

        icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
        for key, candidates in icon_names.items():
            self.icons[key] = None
            for name in candidates:
                path = os.path.join(icons_dir, name)
                if os.path.exists(path):
                    image = self.load_icon_file(path, max_size=18)
                    if image:
                        self.icons[key] = image
                        break

    def load_icon_file(self, path: str, max_size: int = 18) -> Optional[tk.PhotoImage]:
        try:
            img = tk.PhotoImage(file=path)
            width = img.width()
            height = img.height()
            if max(width, height) > max_size:
                factor = max(1, round(max(width, height) / max_size))
                img = img.subsample(factor, factor)
            return img
        except Exception:
            return None

    def apply_theme(self):
        """Apply current theme colors to widgets using Material Design 3 tokens."""
        cols = self.colors.get(self.theme, self.colors['light'])
        surface = cols['surface']
        surface_variant = cols['surface_variant']
        primary = cols['primary']
        on_primary = cols['on_primary']
        on_surface = cols['on_surface']
        on_surface_variant = cols.get('on_surface_variant', on_surface)
        outline = cols['outline']
        outline_variant = cols.get('outline_variant', surface_variant)
        background = cols.get('background', surface)

        # Window and canvas
        try:
            self.root.configure(bg=background)
            self.canvas.configure(bg=surface)
        except Exception:
            pass

        style = ttk.Style()
        try:
            style.theme_use('default')
        except Exception:
            pass

        style.configure('TFrame', background=background)
        style.configure('TLabel', background=background, foreground=on_surface, font=("Segoe UI", 10))
        style.configure('TEntry', fieldbackground=surface, foreground=on_surface)
        style.configure('TButton', background=surface_variant, foreground=on_surface, relief='flat', borderwidth=0, font=("Segoe UI", 10), padding=8)
        style.map(
            'TButton',
            background=[('active', primary), ('disabled', surface_variant)],
            foreground=[('active', on_primary)]
        )

        try:
            self.context_menu.configure(
                background=surface_variant,
                foreground=on_surface,
                activebackground=primary,
                activeforeground=on_primary
            )
        except Exception:
            pass

        if self.theme == 'light':
            if self.icons.get('light'):
                self.theme_btn.config(image=self.icons.get('light'), text='')
            else:
                self.theme_btn.config(image='', text='Light')
        else:
            if self.icons.get('dark'):
                self.theme_btn.config(image=self.icons.get('dark'), text='')
            else:
                self.theme_btn.config(image='', text='Dark')

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        self.theme = 'dark' if self.theme == 'light' else 'light'
        self.apply_theme()

    def pick_default_led_color(self):
        """Open a color picker to choose the default LED color."""
        color = colorchooser.askcolor(color=self.default_led_color, title="Pick default LED color")
        if color and color[1]:
            self.default_led_color = color[1]
            self.refresh_display()
            self.apply_theme()

    def screen_to_world(self, sx: int, sy: int) -> Tuple[int, int]:
        """Convert screen/canvas coordinates to world coordinates (accounting for view offset)."""
        return (sx - self.view_offset[0]) / self.view_scale, (sy - self.view_offset[1]) / self.view_scale

    def world_to_screen(self, wx: int, wy: int) -> Tuple[int, int]:
        """Convert world coordinates to screen/canvas coordinates (accounting for view offset)."""
        return int(wx * self.view_scale + self.view_offset[0]), int(wy * self.view_scale + self.view_offset[1])

    def find_grouping_at(self, x: int, y: int) -> LEDGrouping:
        """Find which grouping is at the given coordinates"""
        for grouping in self.groupings:
            gx, gy = grouping.x, grouping.y
            cols_pixels = grouping.col_modules * (8 * (self.led_size + self.led_gap)) + (grouping.col_modules - 1) * self.module_gap
            rows_pixels = grouping.row_modules * (8 * (self.led_size + self.led_gap)) + (grouping.row_modules - 1) * self.module_gap
            width = cols_pixels + 10
            height = rows_pixels + 35
            
            if gx <= x <= gx + width and gy <= y <= gy + height:
                return grouping
        return None
    
    def find_grouping_at_in_list(self, grouping: LEDGrouping, x: int, y: int) -> LEDGrouping:
        """Check if coordinates are within a specific grouping"""
        gx, gy = grouping.x, grouping.y
        cols_pixels = grouping.col_modules * (8 * (self.led_size + self.led_gap)) + (grouping.col_modules - 1) * self.module_gap
        rows_pixels = grouping.row_modules * (8 * (self.led_size + self.led_gap)) + (grouping.row_modules - 1) * self.module_gap
        width = cols_pixels + 10
        height = rows_pixels + 35
        
        if gx <= x <= gx + width and gy <= y <= gy + height:
            return grouping
        return None
        
    def find_led_at(self, grouping: LEDGrouping, x: int, y: int) -> Tuple[int, int]:
        """Find which LED was clicked in the grouping"""
        gx, gy = grouping.x, grouping.y
        led_start_x = gx + 5
        led_start_y = gy + 30
        
        # Check if click is in LED area
        if x < led_start_x or y < led_start_y:
            return None, None
        
        # Adjust for module gaps
        rel_x = x - led_start_x
        rel_y = y - led_start_y
        
        # Determine which module and position within module
        module_col = 0
        col_in_module = 0
        x_pos = rel_x
        
        for m in range(grouping.col_modules):
            module_width = 8 * (self.led_size + self.led_gap)
            if x_pos < module_width:
                module_col = m
                col_in_module = x_pos // (self.led_size + self.led_gap)
                break
            x_pos -= (module_width + self.module_gap)
        else:
            # Beyond all modules
            return None, None
        
        module_row = 0
        row_in_module = 0
        y_pos = rel_y
        
        for m in range(grouping.row_modules):
            module_height = 8 * (self.led_size + self.led_gap)
            if y_pos < module_height:
                module_row = m
                row_in_module = y_pos // (self.led_size + self.led_gap)
                break
            y_pos -= (module_height + self.module_gap)
        else:
            # Beyond all modules
            return None, None
        
        # Convert to absolute LED position
        col = module_col * 8 + col_in_module
        row = module_row * 8 + row_in_module
        
        if 0 <= row < grouping.rows and 0 <= col < grouping.cols:
            return row, col
        return None, None
        
    def update_properties_panel(self):
        """Update the properties panel for selected grouping"""
        pass  # No longer needed
    
    def show_properties_dialog(self):
        """Show properties dialog for selected grouping"""
        if not self.selected_grouping:
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Properties - {self.selected_grouping.name}")
        dialog.geometry("300x350")
        dialog.resizable(False, False)
        
        # Name
        ttk.Label(dialog, text="Name:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        name_var = tk.StringVar(value=self.selected_grouping.name)
        ttk.Entry(dialog, textvariable=name_var, width=25).grid(row=0, column=1, padx=10, pady=5)
        
        # Ref Char
        ttk.Label(dialog, text="Reference Char:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ref_var = tk.StringVar(value=self.selected_grouping.ref_char)
        ttk.Entry(dialog, textvariable=ref_var, width=3).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Rows (modules)
        ttk.Label(dialog, text="Rows (8x8):").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        rows_var = tk.StringVar(value=str(self.selected_grouping.row_modules))
        ttk.Spinbox(dialog, from_=1, to=4, textvariable=rows_var, width=5).grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Columns (modules)
        ttk.Label(dialog, text="Columns (8x8):").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)
        cols_var = tk.StringVar(value=str(self.selected_grouping.col_modules))
        ttk.Spinbox(dialog, from_=1, to=4, textvariable=cols_var, width=5).grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Round LEDs
        round_var = tk.BooleanVar(value=self.selected_grouping.round_leds)
        ttk.Checkbutton(dialog, text="Round LEDs", variable=round_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=10, pady=5)

        # Custom LED color per grouping
        use_custom_color_var = tk.BooleanVar(value=self.selected_grouping.use_custom_color)
        ttk.Checkbutton(dialog, text="Use custom color for this grouping", variable=use_custom_color_var).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=10, pady=5)

        ttk.Label(dialog, text="Custom Color:").grid(row=6, column=0, sticky=tk.W, padx=10, pady=5)
        custom_color_var = tk.StringVar(value=self.selected_grouping.led_color or self.default_led_color)
        color_entry = ttk.Entry(dialog, textvariable=custom_color_var, width=10)
        color_entry.grid(row=6, column=1, sticky=tk.W, padx=10, pady=5)

        def pick_group_color():
            color = colorchooser.askcolor(color=custom_color_var.get() or self.default_led_color, title="Pick grouping color")
            if color and color[1]:
                custom_color_var.set(color[1])

        ttk.Button(dialog, text="Pick Color", command=pick_group_color).grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=10, pady=5)

        # Buttons
        def apply_changes():
            new_name = name_var.get().strip()
            if new_name and new_name[0].isalpha():
                self.selected_grouping.name = new_name
                self.selected_grouping.ref_char = ref_var.get().strip().upper() or new_name[0].upper()
            else:
                messagebox.showerror("Invalid Name", "Name must start with a letter")
                return
            
            try:
                rows = max(1, min(4, int(rows_var.get())))
                cols = max(1, min(4, int(cols_var.get())))
                self.selected_grouping.row_modules = rows
                self.selected_grouping.col_modules = cols
                self.selected_grouping.__post_init__()
            except ValueError:
                messagebox.showerror("Invalid Value", "Rows and Columns must be numbers 1-4")
                return
            
            self.selected_grouping.round_leds = round_var.get()
            self.selected_grouping.use_custom_color = use_custom_color_var.get()
            self.selected_grouping.led_color = custom_color_var.get().strip() or self.default_led_color
            self.refresh_display()
            dialog.destroy()

        def delete_grouping():
            if messagebox.askyesno("Delete Grouping", "Delete this grouping?"):
                if self.selected_grouping in self.groupings:
                    self.groupings.remove(self.selected_grouping)
                self.selected_grouping = None
                self.refresh_display()
                dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=8, column=0, columnspan=2, padx=10, pady=15)
        ttk.Button(button_frame, text="Apply", command=apply_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, image=self.icons.get('remove'), text=" Remove", compound=tk.LEFT, command=delete_grouping).pack(side=tk.LEFT, padx=5)
    
    def duplicate_grouping(self):
        """Duplicate the selected grouping"""
        if not self.selected_grouping:
            return
        new_grouping = LEDGrouping(
            name=f"{self.selected_grouping.name}_copy",
            x=self.selected_grouping.x + 30,
            y=self.selected_grouping.y + 30,
            row_modules=self.selected_grouping.row_modules,
            col_modules=self.selected_grouping.col_modules,
            round_leds=self.selected_grouping.round_leds,
            ref_char=self.selected_grouping.ref_char,
            leds=[row[:] for row in self.selected_grouping.leds],  # Deep copy
            led_color=self.selected_grouping.led_color,
            use_custom_color=self.selected_grouping.use_custom_color,
            led_colors=([row[:] for row in self.selected_grouping.led_colors] if self.selected_grouping.led_colors is not None else None)
        )
        self.groupings.append(new_grouping)
        self.refresh_display()
    
    def toggle_led_shape_quick(self):
        """Toggle LED shape for selected grouping"""
        if self.selected_grouping:
            self.selected_grouping.round_leds = not self.selected_grouping.round_leds
            self.refresh_display()
        
    def update_name(self):
        """Update the name of selected grouping"""
        pass  # No longer needed
    
    def update_ref_char(self):
        """Update the reference character for selected grouping"""
        pass  # No longer needed
    
    def update_led_shape(self):
        """Update LED shape for selected grouping"""
        pass  # No longer needed
    
    def apply_shape_to_all(self):
        """Apply current LED shape to all groupings"""
        pass  # No longer needed
    
    def update_led_shape(self):
        """Update LED shape for selected grouping"""
        if self.selected_grouping:
            self.selected_grouping.round_leds = self.round_leds_var.get()
            self.refresh_display()
    
    def apply_shape_to_all(self):
        """Apply current LED shape to all groupings"""
        shape = self.round_leds_var.get()
        for grouping in self.groupings:
            grouping.round_leds = shape
        self.refresh_display()
            
    def update_dimensions(self):
        """Update dimensions of selected grouping (in 8x8 modules)"""
        pass  # No longer needed
            
    def refresh_display(self):
        """Redraw the canvas and update listbox"""
        self.canvas.delete("all")
        
        # Draw each grouping
        for i, grouping in enumerate(self.groupings):
            self.draw_grouping(grouping, grouping == self.selected_grouping)
            
    def draw_grouping(self, grouping: LEDGrouping, selected: bool = False):
        """Draw a single grouping on the canvas using world->screen transforms."""
        # World origin for grouping
        gxw, gyw = grouping.x, grouping.y

        # Calculate width/height in world coords with module gaps
        cols_pixels = grouping.col_modules * (8 * (self.led_size + self.led_gap)) + (grouping.col_modules - 1) * self.module_gap
        rows_pixels = grouping.row_modules * (8 * (self.led_size + self.led_gap)) + (grouping.row_modules - 1) * self.module_gap
        width_w = cols_pixels + 10
        height_w = rows_pixels + 35

        cols = self.colors.get(self.theme, self.colors['light'])
        bg_color = cols['surface_variant'] if selected else cols['surface']
        border_color = cols['primary'] if selected else cols['outline']
        title_color = cols['on_surface']
        led_on_color = grouping.led_color if grouping.use_custom_color else self.default_led_color
        led_off_color = '#000000'
        led_outline = cols['outline']
        border_width = 3 if selected else 1

        # Rectangle corners in screen coords
        x1, y1 = self.world_to_screen(gxw, gyw)
        x2, y2 = self.world_to_screen(gxw + width_w, gyw + height_w)
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg_color, outline=border_color, width=border_width)

        # Draw title
        tx, ty = self.world_to_screen(gxw + 8, gyw + 5)
        self.canvas.create_text(tx, ty, anchor=tk.NW, text=grouping.name, font=("Segoe UI", 10, "bold"), fill=title_color)

        # Draw LEDs with module gaps - compute LED positions in world coords then transform
        for row in range(grouping.rows):
            for col in range(grouping.cols):
                module_row = row // 8
                module_col = col // 8
                row_in_module = row % 8
                col_in_module = col % 8

                led_x_w = gxw + 5 + col_in_module * (self.led_size + self.led_gap) + module_col * (8 * (self.led_size + self.led_gap) + self.module_gap)
                led_y_w = gyw + 30 + row_in_module * (self.led_size + self.led_gap) + module_row * (8 * (self.led_size + self.led_gap) + self.module_gap)

                # Convert to screen coords
                sx1, sy1 = self.world_to_screen(led_x_w, led_y_w)
                sx2, sy2 = self.world_to_screen(led_x_w + self.led_size, led_y_w + self.led_size)

                is_on = grouping.leds[row][col]
                if is_on:
                    # prefer per-LED color when provided; otherwise grouping or default
                    if grouping.led_colors is not None and grouping.led_colors[row][col]:
                        color = grouping.led_colors[row][col]
                    else:
                        color = grouping.led_color if grouping.use_custom_color else self.default_led_color
                else:
                    color = led_off_color

                if grouping.round_leds:
                    self.canvas.create_oval(sx1, sy1, sx2, sy2, fill=color, outline=led_outline, width=1)
                else:
                    self.canvas.create_rectangle(sx1, sy1, sx2, sy2, fill=color, outline=led_outline, width=1)
                
    def export_code(self):
        """Export all groupings as C++ byte arrays"""
        if not self.groupings:
            messagebox.showwarning("No Groupings", "Add some LED groupings first!")
            return
            
        code = ""
        for grouping in self.groupings:
            code += self.generate_byte_array(grouping) + "\n"
        
        # Show in dialog
        export_window = tk.Toplevel(self.root)
        export_window.title("Exported Code")
        export_window.geometry("600x500")
        
        text_widget = tk.Text(export_window, wrap=tk.NONE, font=("Courier", 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        text_widget.insert(tk.END, code)
        text_widget.config(state=tk.DISABLED)
        
        button_frame = ttk.Frame(export_window)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(button_frame, text="Copy All", 
                  command=lambda: self.copy_to_clipboard(code)).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Close", 
                  command=export_window.destroy).pack(side=tk.LEFT, padx=2)
                      
    def generate_byte_array(self, grouping: LEDGrouping) -> str:
        """Generate C++ byte arrays for each module in a grouping"""
        code = f"// {grouping.name}\n"
        
        module_num = 1
        # Iterate through modules top to bottom, left to right
        for module_row in range(grouping.row_modules):
            for module_col in range(grouping.col_modules):
                code += f"const byte {grouping.ref_char}{module_num} = {{\n"
                
                # Extract the 8x8 LED data for this module
                for row_in_module in range(8):
                    byte_val = 0
                    for col_in_module in range(8):
                        # Map module-relative position to absolute LED position
                        led_row = module_row * 8 + row_in_module
                        led_col = module_col * 8 + col_in_module
                        
                        if grouping.leds[led_row][led_col]:
                            byte_val |= (1 << (7 - col_in_module))
                    
                    code += f"  0b{byte_val:08b}"
                    if row_in_module < 7:
                        code += ","
                    code += "\n"
                
                code += "}};\n"
                module_num += 1
        
        code += "\n"
        return code
        
    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Code copied to clipboard!")
        
    def save_project(self):
        """Save project to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        
        if filename:
            data = [asdict(g) for g in self.groupings]
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Saved", f"Project saved to {filename}")
            
    def load_project_dialog(self):
        """Load project from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                
                # Handle backward compatibility for old rows/cols format
                self.groupings = []
                for item in data:
                    # Convert old format to new format
                    if 'rows' in item and 'row_modules' not in item:
                        item['row_modules'] = max(1, item['rows'] // 8)
                    if 'cols' in item and 'col_modules' not in item:
                        item['col_modules'] = max(1, item['cols'] // 8)
                    # Remove old keys if they exist
                    item.pop('rows', None)
                    item.pop('cols', None)
                    self.groupings.append(LEDGrouping(**item))
                
                self.selected_grouping = None
                self.refresh_display()
                messagebox.showinfo("Loaded", "Project loaded successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load project: {e}")
                
    def load_project(self):
        """Try to load autosave project"""
        autosave_file = "led_grid_autosave.json"
        if os.path.exists(autosave_file):
            try:
                with open(autosave_file, 'r') as f:
                    data = json.load(f)
                
                # Handle backward compatibility for old rows/cols format
                self.groupings = []
                for item in data:
                    # Convert old format to new format
                    if 'rows' in item and 'row_modules' not in item:
                        item['row_modules'] = max(1, item['rows'] // 8)
                    if 'cols' in item and 'col_modules' not in item:
                        item['col_modules'] = max(1, item['cols'] // 8)
                    # Remove old keys if they exist
                    item.pop('rows', None)
                    item.pop('cols', None)
                    self.groupings.append(LEDGrouping(**item))
                
                self.refresh_display()
            except:
                pass


def main():
    root = tk.Tk()
    app = LEDGridManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
