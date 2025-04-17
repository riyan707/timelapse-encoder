import os
import sys
import time
import datetime
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re

APP_DIR = os.path.abspath(os.path.dirname(__file__))

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tooltip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tooltip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1, font=("Segoe UI", 9))
        label.pack(ipadx=5, ipady=2)

    def hide(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class TimelapseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Timelapse Encoder")
        self.geometry("600x600")

        self.ffmpeg_path = os.path.join(APP_DIR, "ffmpeg", "bin", "ffmpeg.exe")
        if not os.path.exists(self.ffmpeg_path):
            messagebox.showerror("FFmpeg Error", f"Could not find ffmpeg.exe at:\n{self.ffmpeg_path}")
            self.destroy()
            return

        self.observer = None
        self.init_vars()
        self.build_scrollable_ui()

    def init_vars(self):
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="watch")
        self.use_speed = tk.BooleanVar(value=True)
        self.speed_var = tk.StringVar(value="1.0")
        self.target_duration_var = tk.StringVar(value="00:00:10")
        self.actual_length_var = tk.StringVar(value="Actual Length: 00:00:00")
        self.estimated_output_var = tk.StringVar(value="Estimated Length: 00:00:00")
        self.resolution_var = tk.StringVar(value="Original")
        self.crf_var = tk.IntVar(value=23)

    def build_scrollable_ui(self):
        canvas = tk.Canvas(self)
        frame = ttk.Frame(canvas)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        padding = {'padx': 10, 'pady': 5}

        def label(row, text):
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", **padding)

        def entry_with_button(row, text_var, command):
            entry = ttk.Entry(frame, textvariable=text_var, width=45)
            entry.grid(row=row, column=1, sticky="w", **padding)
            ttk.Button(frame, text="Browse", command=command).grid(row=row, column=2, **padding)

        label(0, "Input Folder/File")
        entry_with_button(0, self.input_var, self.choose_input)

        label(1, "Output Folder")
        entry_with_button(1, self.output_var, self.choose_output)

        label(2, "Mode")
        mode_frame = ttk.Frame(frame)
        mode_frame.grid(row=2, column=1, columnspan=2, sticky="w", **padding)
        ttk.Radiobutton(mode_frame, text="Watch", variable=self.mode_var, value="watch").pack(side="left")
        ttk.Radiobutton(mode_frame, text="File", variable=self.mode_var, value="file").pack(side="left")

        label(3, "Encoding Method")
        method_frame = ttk.Frame(frame)
        method_frame.grid(row=3, column=1, columnspan=2, sticky="w", **padding)
        speed_cb = ttk.Checkbutton(method_frame, text="Speed Multiplier", variable=self.use_speed, command=self.toggle_method)
        speed_cb.pack(side="left")
        Tooltip(speed_cb, "Encode using speed multiplier.")

        target_cb = ttk.Checkbutton(method_frame, text="Target Output Length", variable=self.use_speed, onvalue=False, offvalue=True, command=self.toggle_method)
        target_cb.pack(side="left")
        Tooltip(target_cb, "Encode using final output duration instead.")

        label(4, "Speed Multiplier")
        self.speed_entry = ttk.Entry(frame, textvariable=self.speed_var)
        self.speed_entry.grid(row=4, column=1, sticky="ew", **padding)
        Tooltip(self.speed_entry, "How fast the timelapse should be.")

        label(5, "Target Output Length (hh:mm:ss)")
        self.target_entry = ttk.Entry(frame, textvariable=self.target_duration_var)
        self.target_entry.grid(row=5, column=1, sticky="ew", **padding)
        Tooltip(self.target_entry, "How long should the final timelapse be.")

        label(6, "Resolution")
        res_menu = ttk.Combobox(frame, textvariable=self.resolution_var, values=["720p", "1080p", "1440p", "4K", "Original"])
        res_menu.grid(row=6, column=1, sticky="ew", **padding)
        Tooltip(res_menu, "Output resolution.")

        label(7, "CRF Quality")
        crf_spin = ttk.Spinbox(frame, from_=15, to=35, textvariable=self.crf_var)
        crf_spin.grid(row=7, column=1, sticky="ew", **padding)
        Tooltip(crf_spin, "Lower CRF = higher quality (larger size)")

        ttk.Label(frame, textvariable=self.actual_length_var).grid(row=8, column=0, columnspan=3, **padding)
        ttk.Label(frame, textvariable=self.estimated_output_var).grid(row=9, column=0, columnspan=3, **padding)

        ttk.Button(frame, text="Start", command=self.start_process).grid(row=10, column=0, columnspan=3, pady=10)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=11, column=0, columnspan=3, sticky="ew", padx=10, pady=5)

        self.log_box = tk.Text(frame, height=10, bg="#f0f0f0", state="disabled")
        self.log_box.grid(row=12, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

        self.toggle_method()
        self.input_var.trace_add("write", lambda *_: self.update_estimated_length())
        self.speed_var.trace_add("write", lambda *_: self.update_estimated_length())

    def toggle_method(self):
        if self.use_speed.get():
            self.speed_entry.configure(state="normal")
            self.target_entry.configure(state="disabled")
        else:
            self.speed_entry.configure(state="disabled")
            self.target_entry.configure(state="normal")

    def choose_input(self):
        path = filedialog.askdirectory() if self.mode_var.get() == "watch" else filedialog.askopenfilename()
        if path:
            self.input_var.set(path)

    def choose_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def start_process(self):
        if self.mode_var.get() == "file" and os.path.isfile(self.input_var.get()):
            threading.Thread(target=self.encode_video, args=(self.input_var.get(),), daemon=True).start()
        else:
            self.log("[❌] Invalid file path.")

    def wait_until_stable(self, file_path):
        last_size, stable = -1, 0
        while stable < 5:
            try:
                current = os.path.getsize(file_path)
                if current == last_size:
                    stable += 1
                else:
                    stable = 0
                    last_size = current
            except:
                pass
            time.sleep(1)

    def encode_video(self, input_path):
        self.progress.start()
        self.wait_until_stable(input_path)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_name = os.path.join(self.output_var.get(), f"{ts}_timelapse.mp4")
        crf = self.crf_var.get()
        resolution = self.resolution_var.get()

        if self.use_speed.get():
            try:
                speed = float(self.speed_var.get())
            except ValueError:
                self.log("[❌] Invalid speed multiplier entered.")
                self.progress.stop()
                return
        else:
            duration_str = self.target_duration_var.get()
            try:
                h, m, s = map(int, duration_str.split(":"))
                target_secs = h * 3600 + m * 60 + s
                video_secs = self.get_video_length(input_path)
                speed = video_secs / target_secs
            except:
                self.log("[❌] Invalid target output length.")
                self.progress.stop()
                return

        cmd = [
            self.ffmpeg_path, "-i", input_path,
            "-filter:v", f"setpts=PTS/{speed}",
            "-an", "-r", "30", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", str(crf)
        ]

        if resolution.lower() != "original":
            resolutions = {"720p": "1280x720", "1080p": "1920x1080", "1440p": "2560x1440", "4k": "3840x2160"}
            cmd += ["-s", resolutions.get(resolution.lower(), "1920x1080")]
        cmd.append(out_name)

        self.log(f"[🎞️] Encoding to: {out_name}")
        try:
            subprocess.run(cmd, check=True)
            self.log("[✅] Encoding complete.")
        except subprocess.CalledProcessError:
            self.log("[❌] FFmpeg encoding failed.")
        self.progress.stop()

    def get_video_length(self, path):
        try:
            result = subprocess.run([self.ffmpeg_path, "-i", path], stderr=subprocess.PIPE, text=True)
            match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
            if match:
                h, m, s = int(match[1]), int(match[2]), float(match[3])
                return h * 3600 + m * 60 + s
        except:
            pass
        return 0

    def update_estimated_length(self):
        if not os.path.isfile(self.input_var.get()):
            self.actual_length_var.set("Actual Length: 00:00:00")
            self.estimated_output_var.set("Estimated Length: 00:00:00")
            return
        try:
            total_seconds = self.get_video_length(self.input_var.get())
            self.actual_length_var.set(f"Actual Length: {str(datetime.timedelta(seconds=round(total_seconds)))}")
            speed = float(self.speed_var.get())
            est_seconds = int(total_seconds / speed)
            self.estimated_output_var.set(f"Estimated Length: {str(datetime.timedelta(seconds=est_seconds))}")
        except:
            self.estimated_output_var.set("Estimated Length: 00:00:00")
            self.actual_length_var.set("Actual Length: 00:00:00")

if __name__ == "__main__":
    app = TimelapseApp()
    app.mainloop()
