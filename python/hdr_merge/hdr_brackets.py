import os
import sys
import subprocess
import json
import pathlib
import exifread
import OpenImageIO as oiio
from math import log
from tkinter import *
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor
import threading
from time import sleep
import http.client
import urllib

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = pathlib.Path(sys.executable).parent  # Built with cx_freeze
else:
    SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def center(win):
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    # Add 32 to account for titlebar & borders
    y = (win.winfo_screenheight() // 2) - (height+32 // 2)
    win.geometry('{}x{}+{}+{}'.format(width, height, x, y))


def read_json(fp: pathlib.Path) -> dict:
    with fp.open('r') as f:
        s = f.read()
        # Work around invalid JSON when people paste single backslashes in there.
        s = s.replace('\\', '/')
        try:
            return json.loads(s)
        except json.JSONDecodeError as ex:
            raise RuntimeError('Error reading JSON from %s: %s' % (fp, ex))

def get_exe_paths_rez() -> dict:
    exe_paths = {}
    exe_paths['blender_exe'] = 'blender'
    exe_paths['luminance_cli_exe'] = 'rez-env luminance_hdr -- luminance-hdr-cli'
    exe_paths['align_image_stack_exe'] = 'rez-env hugin -- align_image_stack'

    return exe_paths

def get_exe_paths() -> dict:
    global SCRIPT_DIR
    cf = SCRIPT_DIR / 'exe_paths.json'
    default_exe_paths = {
        "blender_exe": "",
        "luminance_cli_exe": "",
        "align_image_stack_exe": ""
    }
    exe_paths = {}
    error = ""
    missing_json_error = "You need to configure some paths first. Edit the '%s' file and fill in the paths." % cf

    if not cf.exists() or cf.stat().st_size == 0:
        with cf.open('w') as f:
            json.dump(default_exe_paths, f, indent=4, sort_keys=True)
        error = missing_json_error + ' (file does not exist or is empty)'
    else:
        exe_paths = read_json(cf)
        for key, path in exe_paths.items():
            if not path:
                error = missing_json_error + ' (%s is empty)' % key
                break
            if not pathlib.Path(path).exists():
                error = "\"%s\" in exe_paths.json either doesn't exist or is an invalid path." % path
    if error:
        print(error)
        input("Press enter to exit.")
        sys.exit(0)
    return exe_paths


EXE_PATHS = get_exe_paths_rez()


def play_sound(sf: str):
    if pathlib.Path(sf).exists():
        try:
            from winsound import PlaySound, SND_FILENAME
        except ImportError:
            pass
        else:
            PlaySound(sf, SND_FILENAME)


def notify_phone(msg="Done"):
    pushover_cfg_f = SCRIPT_DIR / 'pushover.json'
    if not pushover_cfg_f.exists():
        return

    pushover_cfg = read_json(pushover_cfg_f)
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
                 urllib.parse.urlencode({
                     "token": pushover_cfg['token'],
                     "user": pushover_cfg['user'],
                     "message": msg,
                 }), {"Content-type": "application/x-www-form-urlencoded"})
    conn.getresponse()


def chunks(l, n):
    if n < 1:
        n = 1
    return [l[i:i + n] for i in range(0, len(l), n)]


def get_exif(filepath: pathlib.Path):
    if filepath.suffix == '.exr':
        filepath = str(filepath)
        inp = oiio.ImageInput.open(filepath)

        inp_spec = inp.spec()

        resolution = str(inp_spec.width) + 'x' + str(inp_spec.height)

        shutter_speed = inp_spec['ExposureTime']

        try:
            aperture = inp_spec['FNumber']
        except:
            aperture = 0

        iso = int(inp_spec['Exif:ISOSpeedRatings'])

        inp.close()
    else:
        with filepath.open('rb') as f:
            tags = exifread.process_file(f)
        resolution = str(tags["Image ImageWidth"]) + 'x' + \
            str(tags["Image ImageLength"])
        shutter_speed = eval(str(tags["EXIF ExposureTime"]))
        try:
            aperture = eval(str(tags["EXIF FNumber"]))
        except ZeroDivisionError:
            aperture = 0
        iso = int(str(tags["EXIF ISOSpeedRatings"]))
    return {"resolution": resolution, "shutter_speed": shutter_speed, "aperture": aperture, "iso": iso}


def ev_diff(bright_image, dark_image):
    dr_shutter = log(bright_image['shutter_speed'] /
                     dark_image['shutter_speed'], 2)
    try:
        dr_aperture = log(dark_image['aperture'] /
                          bright_image['aperture'], 1.41421)
    except (ValueError, ZeroDivisionError):
        # No lens data means aperture is 0, and we can't divide by 0 :)
        dr_aperture = 0
    dr_iso = log(bright_image['iso']/dark_image['iso'], 2)
    return dr_shutter + dr_aperture + dr_iso


class HDRBrackets(Frame):

    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.master = master

        self.initUI()

    def initUI(self):
        self.master.title("HDR Brackets")
        self.pack(fill=BOTH, expand=True)

        padding = 8
        self.buttons_to_disable = []

        clipboard = ''
        try:
            clipboard = Frame.clipboard_get(self)
        except TclError:
            pass

        # ========== Input ==========
        r1 = Frame(master=self)
        initial_label = "Select a folder..."
        if clipboard:  # if a path is copied in clipboard, fill it in automatically
            try:
                clippath = pathlib.Path(clipboard)
                if clippath.exists():
                    initial_label = clipboard
            except OSError:
                pass  # Not a valid path.

        lbl_input = Label(r1, text="Input Folder:")
        lbl_input.pack(side=LEFT, padx=(padding, 0))

        self.input_folder = Entry(r1)
        self.input_folder.insert(0, initial_label)
        self.input_folder.pack(side=LEFT, fill=X, expand=True, padx=padding)
        self.buttons_to_disable.append(self.input_folder)

        btn_browse = Button(r1, text='Browse', command=self.set_input_folder)
        btn_browse.pack(side=RIGHT, padx=(0, padding))
        self.buttons_to_disable.append(btn_browse)

        r1.pack(fill=X, pady=(padding, 0))
        r2 = Frame(master=self)

        lbl_pattern = Label(r2, text="Matching Pattern:")
        lbl_pattern.pack(side=LEFT, padx=(padding, 0))
        self.extension = Entry(r2, width=6)
        self.extension.insert(0, ".exr")
        self.extension.pack(side=LEFT, padx=(padding/2, 0))
        self.buttons_to_disable.append(self.extension)

        lbl_threads = Label(r2, text="Threads:")
        lbl_threads.pack(side=LEFT, padx=(padding, 0))
        self.num_threads = Spinbox(r2, from_=1, to=9999999, width=2)
        self.num_threads.delete(0, "end")
        self.num_threads.insert(0, "6")
        self.num_threads.pack(side=LEFT, padx=(padding/3, 0))
        self.buttons_to_disable.append(self.num_threads)

        self.do_align = BooleanVar()
        lbl_align = Label(r2, text="Align:")
        lbl_align.pack(side=LEFT, padx=(padding, 0))
        self.align = Checkbutton(
            r2, variable=self.do_align, onvalue=True, offvalue=False)
        self.align.pack(side=LEFT)
        self.buttons_to_disable.append(self.align)

        self.btn_execute = Button(r2, text='Create HDRs', command=self.execute)
        self.btn_execute.pack(side=RIGHT, fill=X, expand=True, padx=padding)
        self.buttons_to_disable.append(self.btn_execute)

        r2.pack(fill=X, pady=(padding, 0))
        r3 = Frame(master=self)

        self.progress = ttk.Progressbar(
            r3, orient=HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=X)

        r3.pack(fill=X, pady=(padding, 0))

    def set_input_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.input_folder.delete(0, END)
            self.input_folder.insert(0, path)
            self.btn_execute['text'] = "Create HDRs"
            self.btn_execute['command'] = self.execute
            self.progress['value'] = 0

    def do_merge(self, blender_exe: str,
                 merge_blend: pathlib.Path, merge_py: pathlib.Path,
                 exifs, out_folder: pathlib.Path,
                 filter_used, i, img_list, folder: pathlib.Path, luminance_cli_exe,
                 align_image_stack_exe):

        exr_folder = out_folder / 'exr'
        jpg_folder = out_folder / 'jpg'
        align_folder = out_folder / 'aligned'

        exr_folder.mkdir(parents=True, exist_ok=True)
        jpg_folder.mkdir(parents=True, exist_ok=True)

        exr_path = exr_folder / ('merged_%03d.exr' % i)
        jpg_path = jpg_folder / exr_path.with_suffix('.jpg').name

        if exr_path.exists():
            print("Skipping set %d, %s exists" % (i, exr_path))
            return

        if self.do_align.get():
            print("Aligning", i)
            align_folder.mkdir(parents=True, exist_ok=True)
            actual_img_list = [i.split("___")[0] for i in img_list]
            cmd = align_image_stack_exe.split(" ")
            cmd += [
                '-i',
                '-l',
                '-a',
                (align_folder / "align_{}_".format(i)).as_posix(),
                '--gpu',
            ]
            cmd += actual_img_list
            new_img_list = []
            for j, img in enumerate(img_list):
                new_img_list.append((align_folder / "align_{}_{}.tif___{}".format(
                    i,
                    str(j).zfill(4),
                    img_list[j].split('___')[-1]
                )).as_posix())
            subprocess.check_call(cmd)
            img_list = new_img_list

        print("Merging", i)

        cmd = [
            blender_exe,
            '--background',
            merge_blend.as_posix(),
            '--factory-startup',
            '--python',
            merge_py.as_posix(),
            '--',
            exifs[0]['resolution'],
            exr_path.as_posix(),
            filter_used,
        ]
        cmd += img_list
        subprocess.check_call(cmd)

        cmd = luminance_cli_exe.split(" ")
        cmd += [
            '-l',
            exr_path.as_posix(),
            '-t',
            'reinhard02',
            '-q',
            '98',
            '-o',
            jpg_path.as_posix(),
        ]
        subprocess.check_call(cmd)

    def execute(self):
        def real_execute():
            folder = pathlib.Path(self.input_folder.get())
            if not folder.exists():
                messagebox.showerror(
                    "Folder does not exist", "The input path you have selected does not exist!")
                return

            print("Starting...")
            self.btn_execute['text'] = "Busy..."
            self.progress['value'] = 0

            for btn in self.buttons_to_disable:
                btn['state'] = 'disabled'

            global EXE_PATHS
            global SCRIPT_DIR
            blender_exe = EXE_PATHS['blender_exe']
            luminance_cli_exe = EXE_PATHS['luminance_cli_exe']
            align_image_stack_exe = EXE_PATHS['align_image_stack_exe']
            merge_blend = pathlib.Path(os.environ.get("REZ_HDR_MERGE_ROOT")) / "blender" / "HDR_Merge.blend"
            merge_py = pathlib.Path(os.environ.get("REZ_HDR_MERGE_ROOT")) / "blender" / "blender_merge.py"

            out_folder = folder / "Merged"
            glob = self.extension.get()
            if '*' not in glob:
                glob = '*%s' % glob
            files = list(folder.glob(glob))

            # Analyze EXIF to determine number of brackets
            exifs = []
            for f in files:
                e = get_exif(f)
                if e in exifs:
                    break
                exifs.append(e)
            brackets = len(exifs)
            print("\nBrackets:", brackets)
            print("Exifs:", exifs)
            evs = [ev_diff({"shutter_speed": 1000000000, "aperture": 0.1,
                           "iso": 1000000000000}, e) for e in exifs]
            evs = [ev-min(evs) for ev in evs]

            filter_used = "None"  # self.filter.get().replace(' ', '').replace('+', '_')  # Depreciated

            # Do merging
            executor = ThreadPoolExecutor(
                max_workers=int(self.num_threads.get()))
            threads = []
            sets = chunks(files, brackets)
            print("Sets:", len(sets), "\n")
            for i, s in enumerate(sets):
                img_list = []
                for ii, img in enumerate(s):
                    img_list.append(img.as_posix()+'___'+str(evs[ii]))

                # self.do_merge (blender_exe, merge_blend, merge_py, exifs, out_folder, filter_used, i, img_list, folder, luminance_cli_exe)
                t = executor.submit(self.do_merge, blender_exe, merge_blend, merge_py, exifs, out_folder,
                                    filter_used, i, img_list, folder, luminance_cli_exe, align_image_stack_exe)
                threads.append(t)

            while any(not t.done() for t in threads):
                sleep(2)
                self.update()
                num_finished = 0

                for tt in threads:
                    if not tt.done():
                        continue
                    try:
                        tt.result()
                    except Exception as ex:
                        print('Exception in thread: %s', ex)
                    num_finished += 1
                progress = (num_finished/len(threads))*100
                print("Progress:", progress)
                self.progress['value'] = int(progress)

            print("Done!!!")
            notify_phone(folder)
            for btn in self.buttons_to_disable:
                btn['state'] = 'normal'
            self.btn_execute['text'] = "Done!"
            self.btn_execute['command'] = self.quit
            play_sound("C:/Windows/Media/Speech On.wav")
            self.update()

        # Run in a separate thread to keep UI alive
        threading.Thread(target=real_execute).start()

    def quit(self):
        global root
        root.destroy()


def main():
    print("This window will report detailed progress of the blender renders.")
    print("Use the other window to start the merging process.")

    global root
    root = Tk()
    root.geometry("450x86")
    center(root)
    # root.iconbitmap(str(SCRIPT_DIR / "icons/icon.ico"))
    app = HDRBrackets(root)
    root.mainloop()


if __name__ == '__main__':
    main()