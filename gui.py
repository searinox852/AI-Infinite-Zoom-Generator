import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
import subprocess
import threading
import sys
import shutil
import tempfile
import webbrowser
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


class InfiniteZoomGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Infinite Zoom Generator")
        self.root.resizable(True, True)
        self.root.minsize(700, 680)

        self.process = None
        self._last_output = None
        self._temp_dir = None
        self._output_user_edited = False
        self._build_ui()
        self._apply_theme()

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", padding=6)
        style.configure("Run.TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("Preview.TButton", font=("Segoe UI", 9, "bold"), padding=6)
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TEntry", font=("Segoe UI", 9))
        style.configure("TCheckbutton", font=("Segoe UI", 9))
        style.configure("TRadiobutton", font=("Segoe UI", 9))
        style.configure("Drop.TEntry", fieldbackground="#1e1e2e")

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)

        # Header
        header = tk.Frame(self.root, bg="#1a1a2e", pady=12)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="AI Infinite Zoom Generator", bg="#1a1a2e", fg="#e0e0ff",
                 font=("Segoe UI", 14, "bold")).pack()
        tk.Label(header, text="Convert image sequences into smooth zoom videos",
                 bg="#1a1a2e", fg="#8888aa", font=("Segoe UI", 9)).pack()

        # Mode selector
        mode_frame = ttk.LabelFrame(self.root, text="Mode", padding=10)
        mode_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 4))
        self._build_mode(mode_frame)

        # Paths
        paths_frame = ttk.LabelFrame(self.root, text="Paths", padding=10)
        paths_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        paths_frame.columnconfigure(1, weight=1)
        self._build_paths(paths_frame)

        # Parameters
        params_frame = ttk.LabelFrame(self.root, text="Parameters", padding=10)
        params_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
        params_frame.columnconfigure(1, weight=1)
        self._build_params(params_frame)

        # Options
        self.opts_frame = ttk.LabelFrame(self.root, text="Options", padding=10)
        self.opts_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=4)
        self._build_options(self.opts_frame)

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Output Log", padding=8)
        log_frame.grid(row=5, column=0, sticky="nsew", padx=12, pady=4)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)
        self._build_log(log_frame)

        # Bottom bar
        bottom = tk.Frame(self.root, pady=8)
        bottom.grid(row=6, column=0, sticky="ew", padx=12)
        bottom.columnconfigure(2, weight=1)
        self._build_bottom(bottom)

    def _build_mode(self, frame):
        self.mode_var = tk.StringVar(value="outpaint")

        ttk.Radiobutton(
            frame, text="Outpaint Sequence  — images are pre-outpainted zoom frames",
            variable=self.mode_var, value="outpaint",
            command=self._on_mode_change,
        ).pack(anchor="w", pady=2)

        ttk.Radiobutton(
            frame, text="Any Images (Crossfade)  — zoom-in + crossfade between any images",
            variable=self.mode_var, value="crossfade",
            command=self._on_mode_change,
        ).pack(anchor="w", pady=2)

    def _on_mode_change(self):
        is_outpaint = self.mode_var.get() == "outpaint"
        # Auto Sort and Debug only make sense in outpaint mode
        state = "normal" if is_outpaint else "disabled"
        self.auto_sort_cb.config(state=state)
        self.debug_cb.config(state=state)
        if not is_outpaint:
            self.auto_sort_var.set(False)
            self.debug_var.set(False)

    def _make_drop_entry(self, parent, textvariable, accept_folders=True, on_set=None):
        entry = ttk.Entry(parent, textvariable=textvariable)
        entry.drop_target_register(DND_FILES)

        def on_drop(event):
            path = event.data.strip().strip("{}")
            p = Path(path)
            target = str(p if (accept_folders and p.is_dir()) else p.parent if accept_folders else p)
            textvariable.set(target)
            entry.config(style="Drop.TEntry")
            self.root.after(400, lambda: entry.config(style="TEntry"))
            if on_set:
                on_set(target)

        entry.dnd_bind("<<Drop>>", on_drop)
        entry.dnd_bind("<<DragEnter>>", lambda e: entry.config(style="Drop.TEntry"))
        entry.dnd_bind("<<DragLeave>>", lambda e: entry.config(style="TEntry"))
        return entry

    def _on_input_set(self, folder_path):
        if self._output_user_edited:
            return
        p = Path(folder_path)
        self.output_var.set(str(p.parent / (p.name + ".mp4")))

    def _build_paths(self, frame):
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value="output.mp4")
        self.output_var.trace_add("write", lambda *_: setattr(self, "_output_user_edited", True))

        ttk.Label(frame, text="Input Folder:").grid(row=0, column=0, sticky="w", pady=3)
        self._make_drop_entry(frame, self.input_var, accept_folders=True,
                              on_set=self._on_input_set
                              ).grid(row=0, column=1, sticky="ew", padx=(8, 4), pady=3)
        ttk.Label(frame, text="← drag & drop", foreground="#556688",
                  font=("Segoe UI", 8, "italic")).grid(row=0, column=2, sticky="w", padx=(0, 4))

        def browse_input():
            folder = filedialog.askdirectory(title="Select input image folder")
            if folder:
                self.input_var.set(folder)
                self._output_user_edited = False
                self._on_input_set(folder)
        ttk.Button(frame, text="Browse…", command=browse_input).grid(row=0, column=3, pady=3)

        ttk.Label(frame, text="Output File/Folder:").grid(row=1, column=0, sticky="w", pady=3)
        self._make_drop_entry(frame, self.output_var, accept_folders=False
                              ).grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=3)
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=1, column=2, columnspan=2, pady=3, sticky="w")
        ttk.Button(btn_frame, text="File…",   command=self._browse_output_file).pack(side="left", padx=(0, 2))
        ttk.Button(btn_frame, text="Folder…", command=self._browse_output_folder).pack(side="left")

    def _browse_output_file(self):
        path = filedialog.asksaveasfilename(title="Save output video as", defaultextension=".mp4",
                                            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")])
        if path:
            self.output_var.set(path)

    def _browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select output frame folder")
        if folder:
            self.output_var.set(folder)

    def _build_params(self, frame):
        params = [
            ("Zoom Factor",  "zoom_factor", 2.0,  1.1,  4.0,   0.01, "%.2f",
             "How far to zoom into each image before transitioning"),
            ("Zoom Steps",   "zoom_steps",  100,   10,   300,   1,    "%d",
             "Frames generated per transition"),
            ("Zoom Crop",    "zoom_crop",   0.80,  0.10, 0.95,  0.01, "%.2f",
             "Edge crop factor — outpaint mode only (0.1–0.95)"),
            ("FPS",          "fps",         60.0,  12.0, 120.0, 0.5,  "%.1f",
             "Frames per second of the output video"),
            ("Delay (sec)",  "delay",       0.0,   0.0,  10.0,  0.1,  "%.1f",
             "Hold duration at start and end of video"),
        ]
        self.param_vars = {}
        self.param_labels = {}
        for i, (label, key, default, lo, hi, step, fmt, tooltip) in enumerate(params):
            ttk.Label(frame, text=f"{label}:").grid(row=i, column=0, sticky="w", pady=4)
            var = tk.DoubleVar(value=default)
            self.param_vars[key] = var
            val_label = ttk.Label(frame, text=fmt % default, width=7, anchor="e")
            val_label.grid(row=i, column=2, padx=(4, 0), pady=4)
            self.param_labels[key] = (val_label, fmt)
            ttk.Scale(frame, from_=lo, to=hi, variable=var, orient="horizontal",
                      command=lambda v, k=key: self._on_slider(k, v)
                      ).grid(row=i, column=1, sticky="ew", padx=(8, 4), pady=4)
            ttk.Label(frame, text=tooltip, foreground="#888888",
                      font=("Segoe UI", 7)).grid(row=i, column=3, sticky="w", padx=(8, 0), pady=4)

    def _on_slider(self, key, value):
        val_label, fmt = self.param_labels[key]
        try:
            v = float(value)
            if fmt == "%d":
                v = round(v)
                self.param_vars[key].set(v)
            val_label.config(text=fmt % v)
        except ValueError:
            pass

    def _build_options(self, frame):
        self.auto_sort_var = tk.BooleanVar(value=False)
        self.reverse_var   = tk.BooleanVar(value=False)
        self.debug_var     = tk.BooleanVar(value=False)
        self.seamless_var  = tk.BooleanVar(value=False)

        row1 = tk.Frame(frame)
        row1.pack(anchor="w", fill="x")
        self.auto_sort_cb = ttk.Checkbutton(
            row1, text="Auto Sort  (detect sequence order automatically — outpaint mode only)",
            variable=self.auto_sort_var)
        self.auto_sort_cb.pack(side="left", pady=2)

        row2 = tk.Frame(frame)
        row2.pack(anchor="w", fill="x")
        ttk.Checkbutton(row2,
            text="Seamless Loop  (append first image at end so video cycles back to start)",
            variable=self.seamless_var).pack(side="left", pady=2)

        row3 = tk.Frame(frame)
        row3.pack(anchor="w", fill="x")
        ttk.Checkbutton(row3, text="Reverse",
                        variable=self.reverse_var).pack(side="left", pady=2)
        self.debug_cb = ttk.Checkbutton(row3, text="   Debug Mode",
                                        variable=self.debug_var)
        self.debug_cb.pack(side="left", pady=2, padx=(16, 0))

    def _build_log(self, frame):
        self.log_text = tk.Text(frame, height=10, font=("Consolas", 9), bg="#111118", fg="#cccccc",
                                insertbackground="white", relief="flat", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.tag_config("error",   foreground="#ff6666")
        self.log_text.tag_config("success", foreground="#66ff99")
        self.log_text.tag_config("info",    foreground="#aaaaff")

    def _build_bottom(self, frame):
        self.run_btn = ttk.Button(frame, text="▶  Run", style="Run.TButton", command=self._run)
        self.run_btn.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(frame, text="Clear Log", command=self._clear_log).grid(row=0, column=1)
        ttk.Button(frame, text="⚙  Generate Sequence…", command=self._open_generate_dialog
                   ).grid(row=0, column=2, padx=(8, 0))
        self.preview_btn = ttk.Button(frame, text="🌐  Open Preview", style="Preview.TButton",
                                      command=self._open_preview, state="disabled")
        self.preview_btn.grid(row=0, column=3, padx=(8, 0))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, foreground="#666699").grid(
            row=0, column=4, sticky="e", padx=(8, 0))
        frame.columnconfigure(4, weight=1)

    def _open_generate_dialog(self):
        def on_complete(folder):
            self.input_var.set(folder)
            self._output_user_edited = False
            self._on_input_set(folder)
            self.mode_var.set("outpaint")
            self._on_mode_change()
            self.auto_sort_var.set(True)
        GenerateSequenceDialog(self.root, on_complete)

    # --- Validation ---

    def _validate(self):
        input_path = self.input_var.get().strip()
        output     = self.output_var.get().strip()

        if not input_path:
            raise ValueError("Input folder is required.")
        inp = Path(input_path)
        if not inp.is_dir():
            raise ValueError(f"Input folder does not exist:\n{input_path}")

        images = [f for f in inp.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        if len(images) < 2:
            raise ValueError(f"Need at least 2 images, found {len(images)}.")

        if not output:
            raise ValueError("Output path is required.")
        out = Path(output)
        if out.suffix == "" and out.resolve() == inp.resolve():
            raise ValueError("Output folder cannot be the same as the input folder.")

        zoom_crop = self.param_vars["zoom_crop"].get()
        if not 0.1 <= zoom_crop <= 0.95:
            raise ValueError("Zoom Crop must be between 0.1 and 0.95.")

        if Path(output).suffix == "":
            if not messagebox.askyesno(
                "No file extension",
                f'"{output}" has no extension.\n\nFrames will be saved as PNGs to that folder instead of creating a video.\n\nContinue? (Add .mp4 to get a video)'
            ):
                raise ValueError("Cancelled — add .mp4 to the output path to generate a video.")

        return inp, output

    # --- Seamless loop ---

    def _prepare_input(self, input_path: Path) -> Path:
        if not self.seamless_var.get():
            return input_path
        images = sorted([f for f in input_path.iterdir() if f.suffix.lower() in IMAGE_EXTS])
        self._cleanup_temp()
        self._temp_dir = tempfile.mkdtemp(prefix="infinitezoom_")
        tmp = Path(self._temp_dir)
        for i, img in enumerate(images):
            shutil.copy2(img, tmp / f"{i:04d}_{img.name}")
        shutil.copy2(images[0], tmp / f"{len(images):04d}_loop_{images[0].name}")
        self._log(f"Seamless loop: {len(images)} images + loop frame → temp folder.", tag="info")
        return tmp

    def _cleanup_temp(self):
        if self._temp_dir and Path(self._temp_dir).exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = None

    # --- Preview ---

    def _generate_preview(self, output: str):
        p = Path(output)
        if not p.suffix:
            return None
        html_path = p.with_suffix(".html")
        html_path.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Infinite Zoom Preview</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#000; display:flex; align-items:center; justify-content:center; height:100vh; }}
  video {{ max-width:100vw; max-height:100vh; object-fit:contain; }}
</style>
</head>
<body>
<video src="{p.name}" autoplay loop muted playsinline></video>
</body>
</html>""", encoding="utf-8")
        return html_path

    def _open_preview(self):
        if self._last_output:
            html = Path(self._last_output).with_suffix(".html")
            if html.exists():
                webbrowser.open(html.as_uri())

    # --- Run ---

    def _run(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._log("Process cancelled.", tag="error")
            self._set_running(False)
            return

        try:
            input_path, output = self._validate()
        except ValueError as e:
            messagebox.showerror("Invalid Parameters", str(e))
            return

        actual_input = self._prepare_input(input_path)

        mode         = self.mode_var.get()
        script       = "crossfade_zoom.py" if mode == "crossfade" else "infinite_zoom.py"
        zoom_factor  = self.param_vars["zoom_factor"].get()
        zoom_steps   = int(round(self.param_vars["zoom_steps"].get()))
        zoom_crop    = self.param_vars["zoom_crop"].get()
        fps          = self.param_vars["fps"].get()
        delay        = self.param_vars["delay"].get()

        cmd = [sys.executable, str(Path(__file__).parent / script),
               "-i", str(actual_input), "-o", output,
               "-zf", str(zoom_factor), "-zs", str(zoom_steps),
               "-zc", f"{zoom_crop:.3f}", "-fps", str(fps), "-d", str(delay)]

        if self.auto_sort_var.get(): cmd.append("-as")
        if self.reverse_var.get():  cmd.append("-rev")
        if self.debug_var.get():    cmd.append("-dbg")

        self._last_output = None
        self.preview_btn.config(state="disabled")
        self._clear_log()
        self._log(f"Mode: {'Crossfade Zoom' if mode == 'crossfade' else 'Outpaint Sequence'}", tag="info")
        self._log("Starting...", tag="info")
        self._log("Command: " + " ".join(f'"{a}"' if " " in a else a for a in cmd), tag="info")
        self._log("", tag=None)
        self._set_running(True)
        threading.Thread(target=self._run_process, args=(cmd, output), daemon=True).start()

    def _run_process(self, cmd, output):
        try:
            env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, bufsize=1, cwd=str(Path(__file__).parent),
                                            env=env, encoding="utf-8")
            for line in self.process.stdout:
                self._log(line.rstrip())
            self.process.wait()
            rc = self.process.returncode

            if rc == 0:
                self._log("\nDone! Output saved.", tag="success")
                self.root.after(0, lambda: self.status_var.set("Done"))
                self._last_output = output
                html = self._generate_preview(output)
                if html:
                    self._log(f"Preview: {html}", tag="info")
                    self.root.after(0, lambda: self.preview_btn.config(state="normal"))
            else:
                self._log(f"\nProcess exited with code {rc}.", tag="error")
                self.root.after(0, lambda: self.status_var.set(f"Error (code {rc})"))
        except Exception as e:
            self._log(f"Error: {e}", tag="error")
            self.root.after(0, lambda: self.status_var.set("Error"))
        finally:
            self._cleanup_temp()
            self.root.after(0, lambda: self._set_running(False))

    def _set_running(self, running):
        if running:
            self.run_btn.config(text="■  Cancel")
            self.status_var.set("Running…")
        else:
            self.run_btn.config(text="▶  Run")
            if self.status_var.get() == "Running…":
                self.status_var.set("Ready")

    def _log(self, text, tag=None):
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", text + "\n", tag or "")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.status_var.set("Ready")


class GenerateSequenceDialog:
    """Dialog to generate an outpainted zoom sequence via ComfyUI."""

    SDXL_MODELS = [
        "juggernautXL_v9Rdphoto2Lightning.safetensors",
        "dreamshaperXL_alpha2Xl10.safetensors",
        "sdXL_v10.safetensors",
        "sd_xl_base_1.0.safetensors",
        "realvisxlV50_v50LightningBakedvae.safetensors",
        "FusionDraw9257_Nebula_SDXL.safetensors",
        "SDXL-PsyAI-v4.safetensors",
        "ponyDiffusionV6XL_v6StartWithThisOne.safetensors",
    ]

    def __init__(self, parent, on_complete):
        self.parent = parent
        self.on_complete = on_complete  # called with output_folder path on success
        self.process = None

        self.win = tk.Toplevel(parent)
        self.win.title("Generate Outpaint Sequence")
        self.win.resizable(True, True)
        self.win.minsize(560, 560)
        self.win.grab_set()
        self._build()

    def _build(self):
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(4, weight=1)

        # Input image
        f1 = ttk.LabelFrame(self.win, text="Input Image", padding=10)
        f1.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        f1.columnconfigure(1, weight=1)
        ttk.Label(f1, text="Image:").grid(row=0, column=0, sticky="w")
        self.img_var = tk.StringVar()
        img_entry = ttk.Entry(f1, textvariable=self.img_var)
        img_entry.grid(row=0, column=1, sticky="ew", padx=(8, 4))
        img_entry.drop_target_register(DND_FILES)
        img_entry.dnd_bind("<<Drop>>", lambda e: self.img_var.set(e.data.strip().strip("{}")))
        ttk.Button(f1, text="Browse…", command=self._browse_image).grid(row=0, column=2)

        # Output folder
        ttk.Label(f1, text="Output Folder:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.out_var = tk.StringVar()
        ttk.Entry(f1, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=(6, 0))
        ttk.Button(f1, text="Browse…", command=self._browse_output).grid(row=1, column=2, pady=(6, 0))

        # Settings
        f2 = ttk.LabelFrame(self.win, text="Settings", padding=10)
        f2.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        f2.columnconfigure(1, weight=1)

        ttk.Label(f2, text="Prompt:").grid(row=0, column=0, sticky="nw", pady=4)
        self.prompt_var = tk.StringVar(value="highly detailed, 8k, cinematic, beautiful")
        ttk.Entry(f2, textvariable=self.prompt_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(f2, text="Levels:").grid(row=1, column=0, sticky="w", pady=4)
        self.levels_var = tk.IntVar(value=4)
        levels_lbl = ttk.Label(f2, text="4", width=4, anchor="e")
        levels_lbl.grid(row=1, column=2, pady=4)
        ttk.Scale(f2, from_=2, to=10, variable=self.levels_var, orient="horizontal",
                  command=lambda v: levels_lbl.config(text=str(int(float(v))))
                  ).grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=4)

        ttk.Label(f2, text="Target Size:").grid(row=2, column=0, sticky="w", pady=4)
        self.size_var = tk.StringVar(value="1024")
        ttk.Combobox(f2, textvariable=self.size_var, values=["512", "768", "1024"],
                     state="readonly", width=8).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=4)

        ttk.Label(f2, text="Model:").grid(row=3, column=0, sticky="w", pady=4)
        self.model_var = tk.StringVar(value=self.SDXL_MODELS[0])
        ttk.Combobox(f2, textvariable=self.model_var, values=self.SDXL_MODELS,
                     state="readonly").grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(f2, text="ComfyUI Host:").grid(row=4, column=0, sticky="w", pady=4)
        self.host_var = tk.StringVar(value="http://127.0.0.1:8188")
        ttk.Entry(f2, textvariable=self.host_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        # Log
        f3 = ttk.LabelFrame(self.win, text="Progress", padding=8)
        f3.grid(row=4, column=0, sticky="nsew", padx=12, pady=4)
        f3.columnconfigure(0, weight=1)
        f3.rowconfigure(0, weight=1)
        self.win.rowconfigure(4, weight=1)

        self.log = tk.Text(f3, height=8, font=("Consolas", 9), bg="#111118", fg="#cccccc",
                           relief="flat", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f3, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.config(yscrollcommand=sb.set)
        self.log.tag_config("success", foreground="#66ff99")
        self.log.tag_config("error",   foreground="#ff6666")
        self.log.tag_config("info",    foreground="#aaaaff")

        # Buttons
        btn_row = tk.Frame(self.win, pady=8)
        btn_row.grid(row=5, column=0, padx=12, sticky="ew")
        btn_row.columnconfigure(1, weight=1)
        self.gen_btn = ttk.Button(btn_row, text="Generate", command=self._generate)
        self.gen_btn.grid(row=0, column=0, padx=(0, 8))
        self.use_btn = ttk.Button(btn_row, text="Use in Main Window", state="disabled",
                                  command=self._use_output)
        self.use_btn.grid(row=0, column=1, sticky="w")
        ttk.Button(btn_row, text="Close", command=self.win.destroy).grid(row=0, column=2)

    def _browse_image(self):
        p = filedialog.askopenfilename(
            title="Select input image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")]
        )
        if p:
            self.img_var.set(p)
            if not self.out_var.get():
                self.out_var.set(str(Path(p).parent / (Path(p).stem + "_sequence")))

    def _browse_output(self):
        p = filedialog.askdirectory(title="Select output folder")
        if p:
            self.out_var.set(p)

    def _generate(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._log("Cancelled.", tag="error")
            self.gen_btn.config(text="Generate")
            return

        img = self.img_var.get().strip()
        out = self.out_var.get().strip()
        if not img or not Path(img).is_file():
            messagebox.showerror("Error", "Please select a valid input image.", parent=self.win)
            return
        if not out:
            messagebox.showerror("Error", "Please select an output folder.", parent=self.win)
            return

        cmd = [
            sys.executable,
            str(Path(__file__).parent / "outpaint_sequence.py"),
            "-i", img,
            "-o", out,
            "-n", str(self.levels_var.get()),
            "-p", self.prompt_var.get(),
            "-m", self.model_var.get(),
            "-s", self.size_var.get(),
            "--host", self.host_var.get(),
        ]

        self._clear_log()
        self._log("Starting ComfyUI outpaint pipeline...", tag="info")
        self.gen_btn.config(text="Cancel")
        self.use_btn.config(state="disabled")
        self._out_folder = out
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    def _run(self, cmd):
        import os as _os
        env = {**_os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env, encoding="utf-8"
            )
            for line in self.process.stdout:
                self._log(line.rstrip())
            self.process.wait()
            if self.process.returncode == 0:
                self._log("\nSequence ready!", tag="success")
                self.win.after(0, lambda: self.use_btn.config(state="normal"))
            else:
                self._log(f"\nFailed (code {self.process.returncode}).", tag="error")
        except Exception as e:
            self._log(f"Error: {e}", tag="error")
        finally:
            self.win.after(0, lambda: self.gen_btn.config(text="Generate"))

    def _use_output(self):
        if self.on_complete:
            self.on_complete(self._out_folder)
        self.win.destroy()

    def _log(self, text, tag=None):
        def _a():
            self.log.config(state="normal")
            self.log.insert("end", text + "\n", tag or "")
            self.log.see("end")
            self.log.config(state="disabled")
        self.win.after(0, _a)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")


def main():
    root = TkinterDnD.Tk()
    InfiniteZoomGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
