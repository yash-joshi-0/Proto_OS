import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from typing import List, Tuple, Dict
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


class LEDGridManager:
    def __init__(self, root):
        self.root = root
        self.root.title("LED Grid Manager")
        self.root.geometry("1200x700")
        
        self.groupings: List[LEDGrouping] = []
        self.selected_grouping: LEDGrouping = None
        self.dragging_grouping: LEDGrouping = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        
        self.led_size = 15  # Size of each LED square in pixels (75% of 20)
        self.led_gap = 2    # Gap between LEDs
        self.module_gap = 4  # Gap between 8x8 modules (1/4 of led_size)
        
        # Create UI
        self.create_widgets()
        self.load_project()
        
    def create_widgets(self):
        """Create the UI layout"""
        # Top control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Add Grouping", command=self.add_grouping).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Export Code", command=self.export_code).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Save Project", command=self.save_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Load Project", command=self.load_project_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=2)
        
        # Canvas for LED display
        self.canvas = tk.Canvas(self.root, bg="white", cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        
        # Create context menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Edit Properties", command=self.show_properties_dialog)
        self.context_menu.add_command(label="Duplicate", command=self.duplicate_grouping)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.remove_grouping)
        self.context_menu.add_command(label="Toggle LED Shape", command=self.toggle_led_shape_quick)
        
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
        # Check groupings from top (end of list) to bottom
        clicked_grouping = None
        for grouping in reversed(self.groupings):
            clicked_grouping = self.find_grouping_at_in_list(grouping, event.x, event.y)
            if clicked_grouping:
                break
        
        if clicked_grouping:
            # Check if clicked on LED
            row, col = self.find_led_at(clicked_grouping, event.x, event.y)
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
                self.drag_offset = (event.x - clicked_grouping.x, event.y - clicked_grouping.y)
                self.selected_grouping = clicked_grouping
                self.refresh_display()
        
    def on_canvas_drag(self, event):
        """Handle canvas drag"""
        if self.dragging_grouping:
            self.dragging_grouping.x = event.x - self.drag_offset[0]
            self.dragging_grouping.y = event.y - self.drag_offset[1]
            self.refresh_display()
            
    def on_canvas_release(self, event):
        """Handle canvas drag release"""
        self.dragging_grouping = None
        
    def on_canvas_motion(self, event):
        """Update cursor based on hover"""
        grouping = self.find_grouping_at(event.x, event.y)
        if grouping:
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="arrow")
    
    def on_canvas_right_click(self, event):
        """Handle right-click on canvas"""
        clicked_grouping = None
        for grouping in reversed(self.groupings):
            clicked_grouping = self.find_grouping_at_in_list(grouping, event.x, event.y)
            if clicked_grouping:
                break
        
        if clicked_grouping:
            self.selected_grouping = clicked_grouping
            self.context_menu.post(event.x_root, event.y_root)
            
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
            self.refresh_display()
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=15)
        ttk.Button(button_frame, text="Apply", command=apply_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
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
            leds=[row[:] for row in self.selected_grouping.leds]  # Deep copy
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
        """Draw a single grouping on the canvas"""
        x, y = grouping.x, grouping.y
        
        # Calculate width/height with module gaps
        cols_pixels = grouping.col_modules * (8 * (self.led_size + self.led_gap)) + (grouping.col_modules - 1) * self.module_gap
        rows_pixels = grouping.row_modules * (8 * (self.led_size + self.led_gap)) + (grouping.row_modules - 1) * self.module_gap
        width = cols_pixels + 10
        height = rows_pixels + 35
        
        bg_color = "#e0e0e0" if selected else "#f0f0f0"
        border_color = "#0066cc" if selected else "#cccccc"
        border_width = 3 if selected else 1
        
        self.canvas.create_rectangle(x, y, x + width, y + height, 
                                    fill=bg_color, outline=border_color, width=border_width)
        
        # Draw title
        title_y = y + 5
        self.canvas.create_text(x + 5, title_y, anchor=tk.NW, text=grouping.name, 
                               font=("Arial", 10, "bold"), fill="black")
        
        # Draw LEDs with module gaps
        led_start_x = x + 5
        led_start_y = y + 30
        
        for row in range(grouping.rows):
            for col in range(grouping.cols):
                # Calculate which module this LED belongs to
                module_row = row // 8
                module_col = col // 8
                row_in_module = row % 8
                col_in_module = col % 8
                
                # Calculate position with module gaps
                led_x = led_start_x + col_in_module * (self.led_size + self.led_gap) + module_col * (8 * (self.led_size + self.led_gap) + self.module_gap)
                led_y = led_start_y + row_in_module * (self.led_size + self.led_gap) + module_row * (8 * (self.led_size + self.led_gap) + self.module_gap)
                
                is_on = grouping.leds[row][col]
                color = "#ff0000" if is_on else "#cccccc"
                
                if grouping.round_leds:
                    # Draw round LED
                    self.canvas.create_oval(led_x, led_y, 
                                           led_x + self.led_size, led_y + self.led_size,
                                           fill=color, outline="#333333", width=1)
                else:
                    # Draw square LED
                    self.canvas.create_rectangle(led_x, led_y, 
                                                led_x + self.led_size, led_y + self.led_size,
                                                fill=color, outline="#333333", width=1)
                
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
