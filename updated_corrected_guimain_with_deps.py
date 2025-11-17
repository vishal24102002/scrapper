import os
import sys
import subprocess
import threading
import time
import queue
import re
import logging
import sqlite3
from datetime import datetime, timedelta
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import Calendar

# Ensure telethon is imported for version checking
import telethon

# Configure logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR if 'BASE_DIR' in locals() else '.', 'app.log'),
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# Print Python executable and Telethon version
print(f"GUI is using Python executable: {sys.executable}")
print(f"Telethon version in GUI: {telethon.__version__}")

# Determine the base directory for the executable or script
if getattr(sys, 'frozen', False):  # If the script is running as a frozen executable
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables
bytes_downloaded = 0
previous_bytes_downloaded = 0  # To calculate speed based on the difference
start_time = 0
scraping_active = False  # Global flag to track scraping state
selected_groups = []
selected_data_types = []
checkbox_vars = {}

# Initialize chats as an empty list; we'll load from file
chats = []

# Define paths relative to the base directory
BASE_DIR = base_dir
GROUPS_FILE_PATH = os.path.join(BASE_DIR, 'selected_groups.txt')
DATA_TYPES_FILE_PATH = os.path.join(BASE_DIR, 'selected_data_types.txt')
SELECTED_DATE_FILE_PATH = os.path.join(BASE_DIR, 'selected_date.txt')
FETCH_NEWS_PY_PATH = os.path.join(BASE_DIR, 'scripts', 'updated_fetch_important_topics.py')
MAIN_PY_PATH = os.path.join(BASE_DIR, 'scripts', 'updated_updated_main.py')
VIDEO_TRANSCRIPTION_PY_PATH = os.path.join(BASE_DIR, 'scripts', 'updated_video_transcription.py')
SCRAPER_PY_PATH = os.path.join(BASE_DIR, 'scripts', 'updated_updated_scraper.py')
TARGET_FOLDER = os.path.join(BASE_DIR, "Database")  # Target folder for the database

# Light indicator colors
IDLE_COLOR = "#FF0000"      # Red
RUNNING_COLOR = "#00FF00"   # Green
ERROR_COLOR = "#FFA500"     # Orange

# Initialize tkinter window
app = ctk.CTk()
app.title("Scraping and Transcription")
app.geometry("1100x600")

# Configure grid weights for resizing
app.grid_rowconfigure(0, weight=1)
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=3)

# Create the left frame
left_frame = ctk.CTkFrame(app, fg_color="#333333")
left_frame.grid(row=0, column=0, sticky="nsew")

# Configure rows in the left frame to expand
for i in range(13):
    left_frame.grid_rowconfigure(i, weight=1)

# Create the right frame
right_frame = ctk.CTkFrame(app, fg_color="#333333")
right_frame.grid(row=0, column=1, sticky="nsew")

# Initialize tkinter variables
scraping_status = tk.StringVar()
scraping_status.set("No scraping in progress.")

# Function to update the status light color
def update_status_light(color):
    status_light.configure(bg=color)

# Function to remove date, time, and INFO from log messages
def remove_log_prefix(text):
    # Remove patterns like '2023-10-12 12:34:56,789 - INFO - '
    return re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - INFO - ', '', text)

# Function to update the textbox
def update_textbox(text):
    global bytes_downloaded
    if not isinstance(text, str):
        text = str(text)

    # Handle bytes downloaded updates from scraper
    if text.startswith("BYTES_DOWNLOADED:"):
        try:
            bytes_downloaded = int(text.split(":")[1].strip())
            logging.debug(f"bytes_downloaded updated to {bytes_downloaded}")
        except ValueError:
            logging.error("Failed to parse bytes_downloaded value.")
        return  # Do not add this line to the textbox

    # Remove date, time, and INFO from log messages
    text = remove_log_prefix(text)

    # Filter out any text related to download speed or time elapsed
    if "Download Speed:" in text or "Time Elapsed:" in text:
        return  # Skip adding to textbox

    news_output_textbox.insert(tk.END, text + "\n")
    news_output_textbox.see(tk.END)  # Auto-scroll to the latest entry

# Function to write selected groups to file
def write_groups_to_file():
    try:
        with open(GROUPS_FILE_PATH, "w") as file:
            file.write("\n".join(chats))
        logging.debug("Group list written to file.")
    except Exception as e:
        logging.error(f"Error writing group list to file: {e}")
        update_textbox(f"Error saving group list: {str(e)}")

def update_selected_groups():
    write_groups_to_file()

def load_groups_from_file():
    global chats
    if os.path.exists(GROUPS_FILE_PATH):
        with open(GROUPS_FILE_PATH, "r") as file:
            chats = [line.strip() for line in file if line.strip()]
        logging.debug(f"Loaded groups from file: {chats}")
    else:
        # Initialize with default groups if the file doesn't exist
        chats = [
            'Fall_of_the_Cabal', 'QDisclosure17', 'galactictruth',
            'STFNREPORT', 'realKarliBonne', 'LauraAbolichannel'
        ]
        write_groups_to_file()
        logging.debug("No groups file found. Starting with default groups.")

# Function to write selected date to file
def write_selected_date(date_str):
    try:
        with open(SELECTED_DATE_FILE_PATH, "w") as file:
            file.write(date_str)
        logging.debug("Selected date written to file.")
    except Exception as e:
        logging.error(f"Error writing selected date: {e}")
        update_textbox(f"Error saving selected date: {str(e)}")

# Helper Function: Determine the correct command to execute subprocesses
def get_python_command(script_name):
    """
    Returns the appropriate command to execute a Python script based on the execution context.
    """
    if getattr(sys, 'frozen', False):
        # When the application is frozen, scripts are accessible via sys._MEIPASS/scripts
        script_path = os.path.join(sys._MEIPASS, 'scripts', script_name)
    else:
        # When running as a script, use the scripts folder relative to the main script
        script_path = os.path.join(BASE_DIR, 'scripts', script_name)

    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script {script_name} not found at {script_path}")

    # Use 'python' to execute the script
    return ['python', script_path]

# Function to select all groups or deselect all
def select_all_groups(select_all_var):
    global selected_groups
    if select_all_var.get():
        selected_groups = chats[:]  # Select all groups
        for group, var in checkbox_vars.items():
            var.set(True)  # Check all checkboxes
    else:
        selected_groups = []  # Deselect all groups
        for group, var in checkbox_vars.items():
            var.set(False)  # Uncheck all checkboxes
    update_textbox(f"Selected groups: {', '.join(selected_groups)}")

# Function to toggle the group selection
def toggle_group(group_name, var):
    if var.get():
        if group_name not in selected_groups:
            selected_groups.append(group_name)
    else:
        if group_name in selected_groups:
            selected_groups.remove(group_name)
    update_selected_groups()
    update_textbox(f"Current selection: {', '.join(selected_groups)}")

# Function to create multi-select dropdown (using checkbuttons)
def open_multi_select():
    top = tk.Toplevel(app)
    top.title("Select Groups")
    top.geometry("300x400")

    select_all_var = tk.BooleanVar()

    # Create a frame for the checkboxes to be scrollable
    frame = tk.Frame(top)
    frame.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')

    # Make the frame expandable
    top.grid_rowconfigure(0, weight=1)
    top.grid_columnconfigure(0, weight=1)

    # Scrollable canvas
    canvas = tk.Canvas(frame)
    scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    # Make the inner frame expandable
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    # Select All Checkbutton
    select_all_chk = tk.Checkbutton(
        scrollable_frame,
        text="Select All",
        variable=select_all_var,
        command=lambda: select_all_groups(select_all_var)
    )
    select_all_chk.grid(row=0, column=0, padx=10, pady=5, sticky="w")

    # Checkbuttons for each group in the scrollable frame
    for idx, group in enumerate(chats):
        var = tk.BooleanVar()
        if group in selected_groups:
            var.set(True)
        checkbox_vars[group] = var  # Store the variable in the dictionary
        chk = tk.Checkbutton(
            scrollable_frame,
            text=group,
            variable=var,
            command=lambda g=group, v=var: toggle_group(g, v)
        )
        chk.grid(row=idx+1, column=0, padx=10, pady=5, sticky="w")

# Function to add a new group from the Telegram link input
def add_group():
    group_link = group_input.get()
    if group_link.startswith("https://t.me/") or group_link.startswith("t.me/"):
        if "joinchat" in group_link:
            update_textbox("Cannot add private groups or invite links.")
            logging.warning(f"Attempted to add a private group or invite link: {group_link}")
            return
        group_name = group_link.split("/")[-1]
        if group_name not in chats:
            chats.append(group_name)  # Add the new group to the chat list
            write_groups_to_file()  # Save updated group list to file
            update_textbox(f"Added new group: {group_name}")
            logging.debug(f"Added new group: {group_name}")
            # Update the group selection
            selected_groups.append(group_name)
            checkbox_vars[group_name] = tk.BooleanVar(value=True)
            update_selected_groups()
        else:
            update_textbox(f"Group '{group_name}' is already in the list.")
            logging.warning(f"Attempted to add duplicate group: {group_name}")
    else:
        update_textbox("Invalid Telegram link. Make sure it starts with 'https://t.me/'.")
        logging.warning(f"Invalid Telegram link entered: {group_link}")

# Function to remove a group from the chat list
def remove_group():
    group_link = group_input.get()
    if group_link.startswith("https://t.me/") or group_link.startswith("t.me/"):
        group_name = group_link.split("/")[-1]
        if group_name in chats:
            chats.remove(group_name)  # Remove the group from the chat list
            if group_name in selected_groups:
                selected_groups.remove(group_name)
            if group_name in checkbox_vars:
                del checkbox_vars[group_name]
            write_groups_to_file()  # Save updated group list to file
            update_textbox(f"Removed group: {group_name}")
            logging.debug(f"Removed group: {group_name}")
        else:
            update_textbox(f"Group '{group_name}' not found in the list.")
            logging.warning(f"Attempted to remove non-existent group: {group_name}")
    else:
        update_textbox("Invalid Telegram link. Make sure it starts with 'https://t.me/'.")
        logging.warning(f"Invalid Telegram link entered for removal: {group_link}")

# Load groups from file on startup
load_groups_from_file()
selected_groups = chats[:]  # Initialize selected groups with all chats

# Function to save selected data types to a file
def save_selected_data_types(selected_data_types):
    try:
        with open(DATA_TYPES_FILE_PATH, "w") as file:
            for data_type in selected_data_types:
                file.write(data_type + "\n")
        logging.debug("Selected data types written to file.")
    except Exception as e:
        logging.error(f"Error saving selected data types: {e}")
        update_textbox(f"Error saving selected data types: {str(e)}")

# Function to handle data selection
def handle_data_selection():
    global selected_data_types  # Declare as global to modify it
    options = ["Images", "Videos", "Audios", "Text","Links"]  # Corrected to match scraper.py
    checkbox_vars_dt = {}
    select_all_state = False  # Initial state of select all button

    def update_selection_label():
        selected = [option for option in options if checkbox_vars_dt[option].get()]
        selection_label.configure(text=f"Current Selection: {', '.join(selected)}")

    def toggle_option(option):
        update_selection_label()

    def select_all():
        nonlocal select_all_state
        select_all_state = not select_all_state  # Toggle the state
        for option in options:
            checkbox_vars_dt[option].set(select_all_state)
        update_selection_label()

    def show_selection():
        global selected_data_types  # Declare as global to modify it
        selected_data_types = [option for option in options if checkbox_vars_dt[option].get()]
        selection_label.configure(text=f"Current Selection: {', '.join(selected_data_types)}")  # Update label
        # Save selected data types to file
        save_selected_data_types(selected_data_types)
        selection_window.destroy()  # Close the selection window
        logging.debug(f"Selected data types: {selected_data_types}")

    # Create new window for options
    selection_window = ctk.CTkToplevel(app)
    selection_window.title("Select Data Type to Scrape")
    selection_window.geometry("300x250+500+200")  # Adjust window size
    selection_window.grab_set()

    # Add checkboxes for options
    for idx, option in enumerate(options):
        checkbox_var = tk.BooleanVar()
        checkbox_vars_dt[option] = checkbox_var
        checkbox = ctk.CTkCheckBox(
            selection_window,
            text=option,
            variable=checkbox_var,
            command=lambda opt=option: toggle_option(opt)
        )
        checkbox.grid(row=idx, column=0, padx=20, pady=5, sticky="w")

    # Add buttons for "Select All" and "Confirm"
    select_all_btn = ctk.CTkButton(selection_window, text="Select All", command=select_all)
    select_all_btn.grid(row=len(options), column=0, padx=20, pady=10)

    confirm_btn = ctk.CTkButton(selection_window, text="Confirm", command=show_selection)
    confirm_btn.grid(row=len(options) + 1, column=0, padx=20, pady=10)

# Function to run the scraping process
def run_scraping_process(text_queue):
    global scraping_active, bytes_downloaded, start_time, selected_date

    try:
        # Prepare command-line arguments
        scraper_command = get_python_command('updated_updated_scraper.py')

        # Add the selected groups, data types, and date as command-line arguments
        groups_arg = ','.join(selected_groups)
        datatypes_arg = ','.join(selected_data_types)
        date_arg = selected_date.strftime('%Y-%m-%d')

        scraper_command += ['--groups', groups_arg, '--datatypes', datatypes_arg, '--dates', date_arg]

        # If a target folder is specified, add it
        scraper_command += ['--target_folder', TARGET_FOLDER]

    except FileNotFoundError as e:
        text_queue.put(str(e))
        update_status_light(ERROR_COLOR)
        logging.error(str(e))
        scraping_active = False
        return
    except Exception as e:
        text_queue.put(f"Unexpected error: {str(e)}")
        update_status_light(ERROR_COLOR)
        logging.error(f"Unexpected error: {e}")
        scraping_active = False
        return

    logging.debug(f"Starting scraper subprocess with: {' '.join(scraper_command)}")
    update_textbox(f"Starting scraper subprocess with: {' '.join(scraper_command)}")

    # Initialize bytes_downloaded before starting
    bytes_downloaded = 0

    try:
        process = subprocess.Popen(
            scraper_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            shell=False,
            cwd=os.path.join(sys._MEIPASS, 'scripts') if getattr(sys, 'frozen', False) else os.path.dirname(SCRAPER_PY_PATH)
        )

        # Capture stdout and send it to the queue
        for stdout_line in iter(process.stdout.readline, ""):
            if stdout_line:
                text_queue.put(stdout_line.strip())

        process.stdout.close()
        process.wait()

        if process.returncode != 0:
            text_queue.put(f"Scraping subprocess exited with code {process.returncode}.")
            update_status_light(ERROR_COLOR)
            logging.error(f"Scraping subprocess exited with code {process.returncode}.")
        else:
            text_queue.put(f"Scraping subprocess has completed successfully.")
            update_status_light(IDLE_COLOR)
            logging.info("Scraping subprocess completed successfully.")

        # Calculate total time elapsed and average download speed
        total_time_elapsed = time.time() - start_time
        elapsed_td = timedelta(seconds=int(total_time_elapsed))
        if bytes_downloaded > 0 and total_time_elapsed > 0:
            average_speed = bytes_downloaded / total_time_elapsed
            average_speed_mb = average_speed / (1024 * 1024)
            text_queue.put(f"Total time elapsed: {str(elapsed_td)}")
            text_queue.put(f"Average download speed: {average_speed_mb:.2f} MB/s")
        else:
            text_queue.put(f"Total time elapsed: {str(elapsed_td)}")
            text_queue.put("Average download speed: 0.00 MB/s (No data downloaded)")

    except Exception as e:
        text_queue.put(f"Error: {str(e)}")
        update_status_light(ERROR_COLOR)
        logging.error(f"Error in scraper subprocess: {e}")

    scraping_active = False
    logging.debug("Scraping process set to inactive.")


# Update textbox function via app.after()
def update_textbox_from_queue(text_queue):
    try:
        while True:
            text = text_queue.get_nowait()
            update_textbox(text)
    except queue.Empty:
        pass
    if scraping_active:
        app.after(100, lambda: update_textbox_from_queue(text_queue))

# Function to start scraping
def start_scraping():
    global selected_data_types, scraping_active, bytes_downloaded
    global previous_bytes_downloaded, start_time, selected_date

    if scraping_active:
        update_textbox("Scraping is already in progress.")
        logging.warning("Attempted to start scraping while already active.")
        return

    if not selected_groups:
        update_textbox("Error: No groups selected for scraping.")
        logging.error("No groups selected for scraping.")
        return

    if not selected_data_types:
        update_textbox("Error: No data types selected for scraping.")
        logging.error("No data types selected for scraping.")
        return

    if not selected_date:
        update_textbox("No date selected for scraping.")
        logging.error("No date selected for scraping.")
        return

    # Check for today's or future dates
    today = datetime.utcnow().date()
    if selected_date >= today:
        update_textbox("Cannot scrape today's or future date's data.")
        logging.error("Attempted to scrape today's or future date's data.")
        return

    scraping_active = True
    logging.debug("Scraping process started.")
    update_textbox("Scraping process started.")

    # Set status light to green (running)
    update_status_light(RUNNING_COLOR)

    # Construct status message
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    status_message = f"Status -> Target Group: [{', '.join(selected_groups)}], Datatype: [{', '.join(selected_data_types)}], Date: [{selected_date_str}]"

    # Set scraping status and update textbox
    scraping_status.set(status_message)
    update_textbox(scraping_status.get())

    # Initialize timing and bytes tracking
    start_time = time.time()
    bytes_downloaded = 0
    previous_bytes_downloaded = 0

    # Start updating elapsed time label
    update_elapsed_label()

    # Create a queue for capturing output
    text_queue = queue.Queue()

    # Start the scraping process in a separate thread
    scraping_thread = threading.Thread(target=run_scraping_process, args=(text_queue,), daemon=True)
    scraping_thread.start()
    logging.debug("Scraping thread started.")

    # Start updating the textbox from the queue
    update_textbox_from_queue(text_queue)


def run_fetch_news():
    try:
        try:
            # Construct the command to run googletrends.py
            fetch_news_command = get_python_command('googletrends.py')
        except FileNotFoundError as e:
            update_textbox(str(e))
            update_status_light(ERROR_COLOR)
            logging.error(str(e))
            return
        except Exception as e:
            update_textbox(f"Unexpected error: {str(e)}")
            update_status_light(ERROR_COLOR)
            logging.error(f"Unexpected error: {e}")
            return

        logging.debug(f"Starting fetch news subprocess with: {' '.join(fetch_news_command)}")
        update_textbox(f"Starting fetch news subprocess with: {' '.join(fetch_news_command)}")

        process = subprocess.Popen(
            fetch_news_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            shell=False,  # Ensure shell=False for security and compatibility
            cwd=os.path.join(sys._MEIPASS, 'scripts') if getattr(sys, 'frozen', False) else os.path.dirname(FETCH_NEWS_PY_PATH)
        )

        stdout, _ = process.communicate()

        if process.returncode != 0:
            update_textbox(f"Fetch news subprocess exited with code {process.returncode}.")
            update_status_light(ERROR_COLOR)
            logging.error(f"Fetch news subprocess exited with code {process.returncode}.")
        else:
            update_textbox(stdout)
            update_status_light(IDLE_COLOR)
            logging.info("Fetch news subprocess completed successfully.")

    except Exception as e:
        update_textbox(f"Error: {str(e)}")
        update_status_light(ERROR_COLOR)
        logging.error(f"Error in fetch news subprocess: {e}")


# Function to start fetch news in a separate thread
def start_fetch_news_thread():
    if not selected_date:
        update_textbox("No date selected for fetching news.")
        logging.error("No date selected for fetching news.")
        return
    date_folder = selected_date
    threading.Thread(target=run_fetch_news, args=(date_folder,), daemon=True).start()
    logging.debug("Fetch news thread started.")

# Function to browse and select target folder
def browse_target_folder():
    global TARGET_FOLDER
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        TARGET_FOLDER = folder_selected
        folder_input.configure(state=tk.NORMAL)
        folder_input.delete(0, tk.END)
        folder_input.insert(0, TARGET_FOLDER)
        folder_input.configure(state=tk.DISABLED)
        logging.debug(f"Target folder selected: {TARGET_FOLDER}")
    else:
        TARGET_FOLDER = BASE_DIR
        folder_input.configure(state=tk.NORMAL)
        folder_input.delete(0, tk.END)
        folder_input.insert(0, "Default: " + BASE_DIR)
        folder_input.configure(state=tk.DISABLED)
        logging.debug("Default target folder restored.")

# Function to start transcription
def start_transcription():
    try:
        transcription_command = get_python_command('updated_video_transcription.py')
        subprocess.Popen(transcription_command, shell=False)
        messagebox.showinfo("Transcription", "Transcription has started.")
        logging.info("Transcription subprocess started.")
    except FileNotFoundError as e:
        messagebox.showerror("Error", f"Failed to start transcription: {str(e)}")
        logging.error(f"Failed to start transcription: {e}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start transcription: {str(e)}")
        logging.error(f"Failed to start transcription: {e}")

# Function to update elapsed label
def update_elapsed_label():
    if not scraping_active:
        elapsed_label.configure(text="Time Elapsed: 00:00:00")
        return
    elapsed_time = time.time() - start_time
    elapsed_td = timedelta(seconds=int(elapsed_time))
    elapsed_str = str(elapsed_td)
    elapsed_label.configure(text=f"Time Elapsed: {elapsed_str}")
    app.after(1000, update_elapsed_label)

# Adding components to the left frame
group_label = ctk.CTkLabel(left_frame, text="Enter Telegram Link:")
group_label.grid(row=0, column=0, padx=10, pady=10, sticky='ew')

group_input = ctk.CTkEntry(left_frame)
group_input.grid(row=1, column=0, padx=10, pady=10, sticky='ew', columnspan=2)

# Set a consistent width for buttons and align them properly
button_width = 100

# Add Group and Remove Group buttons
add_group_btn = ctk.CTkButton(
    left_frame, text="Add Group", command=add_group, width=button_width
)
add_group_btn.grid(row=2, column=0, padx=5, pady=5, sticky='ew')

remove_group_btn = ctk.CTkButton(
    left_frame, text="Remove Group", command=remove_group, width=button_width
)
remove_group_btn.grid(row=2, column=1, padx=5, pady=5, sticky='ew')

# Select Groups button
select_groups_btn = ctk.CTkButton(
    left_frame, text="1.Select Groups", command=open_multi_select, width=button_width
)
select_groups_btn.grid(row=3, column=0, padx=5, pady=5, sticky='ew', columnspan=2)

# Select Datatype button
data_type_button = ctk.CTkButton(
    left_frame, text="2. Select Datatype", command=handle_data_selection, width=button_width
)
data_type_button.grid(row=4, column=0, padx=5, pady=5, sticky='ew', columnspan=2)

# Start Scraping button
start_scraping_btn = ctk.CTkButton(
    left_frame, text="5. Start Scraping", command=start_scraping
)
start_scraping_btn.grid(row=5, column=0, padx=5, pady=5, sticky='ew')

# Start Transcription button
transcription_button = ctk.CTkButton(
    left_frame, text="Start Transcription", command=start_transcription
)
transcription_button.grid(row=5, column=1, padx=5, pady=5, sticky='ew')

# Folder selection components
folder_label = ctk.CTkLabel(
    left_frame,
    text="Select Target Folder for " + os.path.join(base_dir, "Database") + ":"
)
folder_label.grid(row=6, column=0, padx=10, pady=10, sticky='ew', columnspan=2)

folder_input = ctk.CTkEntry(left_frame, state=tk.DISABLED)
folder_input.grid(row=7, column=0, padx=10, pady=10, sticky='ew', columnspan=2)
folder_input.insert(0, "Default: " + BASE_DIR)

folder_browse_button = ctk.CTkButton(
    left_frame, text="3. Browse Target Folder", command=browse_target_folder
)

# Function to set the selected folder as the default base directory
def set_default_directory():
    global BASE_DIR
    BASE_DIR = TARGET_FOLDER
    messagebox.showinfo('Set Default', f'The folder {TARGET_FOLDER} has been set as the default directory.')
    logging.info(f"Default directory set to: {TARGET_FOLDER}")

# Adding 'Set Default' button below 'Browse' button
set_default_button = ctk.CTkButton(
    left_frame, text='Set Default', command=set_default_directory
)
set_default_button.grid(row=8, column=1, padx=10, pady=(2, 0))
folder_browse_button.grid(row=8, column=0, padx=10, pady=2, sticky='ew')

# Adding the selection label
selection_label = ctk.CTkLabel(left_frame, text="Current Selection: None")
selection_label.grid(row=9, column=0, padx=10, pady=1, sticky='ew', columnspan=2)

calendar_label = ctk.CTkLabel(left_frame, text="4. Select Date:")
calendar_label.grid(row=10, column=0, padx=10, pady=10, sticky='ew')

# Create the Calendar widget with single selection
calendar = Calendar(left_frame, selectmode="day", tooltipdelay=-1)
calendar.grid(row=11, column=0, padx=10, pady=10, sticky='ew', columnspan=2)

# Initialize selected_date variable
selected_date = None

# Function to handle date clicks (single selection)
def on_date_click(event):
    global selected_date
    try:
        date = calendar.selection_get()
    except:
        return  # No date selected

    # If a date was previously selected, remove its highlight
    if selected_date:
        calendar.calevent_remove('all')  # Remove all calendar events

    # If the clicked date is the same as the currently selected date, deselect it
    if selected_date == date:
        selected_date = None
        update_textbox("No date selected.")
        logging.info("Date deselected.")
    else:
        # Highlight the new selected date
        selected_date = date
        calendar.calevent_create(date, 'Selected', tags='selected')
        update_textbox(f"Selected date: {selected_date.strftime('%Y-%m-%d')}")
        logging.info(f"Date selected: {selected_date.strftime('%Y-%m-%d')}")

# Bind the event handler to the Calendar
calendar.bind('<<CalendarSelected>>', on_date_click)

fetch_news_btn = ctk.CTkButton(
    left_frame, text="Fetch News", command=start_fetch_news_thread
)
fetch_news_btn.grid(row=12, column=0, padx=10, pady=10, sticky='ew', columnspan=2)

# Adding components to the right frame
news_output_label = ctk.CTkLabel(right_frame, text="News Output:")
news_output_label.grid(row=0, column=0, padx=10, pady=10, sticky='ew')

news_output_textbox = tk.Text(right_frame, height=25)
news_output_textbox.grid(row=1, column=0, padx=10, pady=10, sticky='nsew')

elapsed_label = ctk.CTkLabel(right_frame, text="Time Elapsed: 00:00:00")
elapsed_label.grid(row=3, column=0, padx=10, pady=5, sticky='ew')

# Configure the right frame to allow it to expand
right_frame.grid_rowconfigure(1, weight=1)

# Adding the light indicator
status_light = tk.Label(left_frame, text="", bg=IDLE_COLOR, width=2, height=1)
status_light.place(x=10, y=20)

# Start the tkinter mainloop
logging.info("Starting GUI...")
print("Starting GUI...")
app.mainloop()
print("GUI Ended.")
logging.info("GUI Ended.")

# Retry mechanism for database connection
def connect_to_database_with_retry(db_path, retries=5, delay=2):
    """
    Attempts to connect to the SQLite database with retries in case of a locked database.
    """
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(db_path, timeout=30)  # Increase timeout for connection
            logging.debug(f"Connected to database at {db_path} on attempt {attempt + 1}.")
            return conn
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                logging.warning(f"Database locked. Retry {attempt + 1} in {delay} seconds.")
                time.sleep(delay)  # Wait before retrying
            else:
                logging.error(f"Database connection error: {e}")
                raise e
    raise sqlite3.OperationalError("Failed to connect to database after multiple retries.")
