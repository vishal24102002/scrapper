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
import telethon
import ffmpeg
from vosk import Model, KaldiRecognizer
import json

BASE_DIR = r"C:\\Users\\Ashutosh Mishra\\Desktop\\STUDY\\Coding\\goldenagemeditations project\\dynamic path"
TARGET_FOLDER = r"C:\\Users\\Ashutosh Mishra\\Desktop\\STUDY\\Coding\\goldenagemeditations project\\dynamic path\\Database"
# Path to the Vosk model
if getattr(sys, 'frozen', False):  # If the script is running as a frozen executable
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

VOSK_MODEL_PATH = os.path.join(BASE_DIR, 'vosk-model-en-us-0.22')

# Check if the Vosk model exists
if not os.path.exists(VOSK_MODEL_PATH):
    logging.error(f"Vosk model not found at {VOSK_MODEL_PATH}. Please ensure the model is downloaded and placed correctly.")
    messagebox.showerror("Model Not Found", f"Vosk model not found at {VOSK_MODEL_PATH}. Please ensure the model is downloaded and placed correctly.")

# Initialize global flags
transcription_active = False  # Global flag to track transcription state

# Function to transcribe a single audio file
def transcribe_audio(audio_path, model):
    try:
        wf = open(audio_path, "rb")
        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(True)
        
        while True:
            data = wf.read(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                pass  # You can handle partial results here if needed
        result = rec.FinalResult()
        result_dict = json.loads(result)
        transcription = result_dict.get("text", "")
        wf.close()
        return transcription
    except Exception as e:
        logging.error(f"Error transcribing {audio_path}: {e}")
        return f"Error transcribing {audio_path}: {e}"

# Function to convert video to audio using ffmpeg
def convert_video_to_audio(video_path, audio_path):
    try:
        ffmpeg.input(video_path).output(audio_path, format='wav', ac=1, ar='16000').overwrite_output().run(quiet=True)
        return True
    except ffmpeg.Error as e:
        logging.error(f"ffmpeg error for {video_path}: {e}")
        return False

# Function to run the transcription process
def run_transcription_process(text_queue, selected_date):
    global transcription_active  # Reusing transcription_active to indicate transcription status

    try:
        if not selected_date:
            text_queue.put("No date selected for transcription.")
            logging.error("No date selected for transcription.")
            return

        # Path to the selected date folder
        date_folder_path = os.path.join(TARGET_FOLDER, selected_date.strftime("%Y-%m-%d"))

        if not os.path.exists(date_folder_path):
            text_queue.put(f"Selected date folder does not exist: {date_folder_path}")
            logging.error(f"Selected date folder does not exist: {date_folder_path}")
            return

        # Load the Vosk model
        model = Model(VOSK_MODEL_PATH)
        text_queue.put("Vosk model loaded successfully.")
        logging.info("Vosk model loaded successfully.")

        # Traverse each Telegram group folder
        for group in selected_groups:
            group_folder = os.path.join(date_folder_path, group)
            videos_folder = os.path.join(group_folder, "Videos")

            if not os.path.exists(videos_folder):
                text_queue.put(f"No 'Videos' folder found for group: {group}")
                logging.warning(f"No 'Videos' folder found for group: {group}")
                continue

            # Create Transcriptions folder if it doesn't exist
            transcriptions_folder = os.path.join(videos_folder, "Transcriptions")
            os.makedirs(transcriptions_folder, exist_ok=True)

            # Iterate over all video files in the Videos folder
            for video_file in os.listdir(videos_folder):
                video_path = os.path.join(videos_folder, video_file)

                # Check if the file is a video (you can extend this with more video formats)
                if not video_file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                    continue

                text_queue.put(f"Processing video: {video_file}")
                logging.info(f"Processing video: {video_file}")

                # Define paths for the audio and transcription files
                audio_filename = os.path.splitext(video_file)[0] + ".wav"
                audio_path = os.path.join(videos_folder, audio_filename)
                transcription_filename = os.path.splitext(video_file)[0] + ".txt"
                transcription_path = os.path.join(transcriptions_folder, transcription_filename)

                # Convert video to audio
                if convert_video_to_audio(video_path, audio_path):
                    text_queue.put(f"Converted {video_file} to audio.")
                    logging.info(f"Converted {video_file} to audio.")

                    # Transcribe audio
                    transcription = transcribe_audio(audio_path, model)
                    if transcription:
                        with open(transcription_path, "w", encoding='utf-8') as f:
                            f.write(transcription)
                        text_queue.put(f"Transcription saved: {transcription_filename}")
                        logging.info(f"Transcription saved: {transcription_filename}")
                    else:
                        text_queue.put(f"Failed to transcribe: {video_file}")
                        logging.error(f"Failed to transcribe: {video_file}")

                    # Remove the temporary audio file
                    os.remove(audio_path)
                    logging.debug(f"Removed temporary audio file: {audio_path}")
                else:
                    text_queue.put(f"Failed to convert {video_file} to audio.")
                    logging.error(f"Failed to convert {video_file} to audio.")

        text_queue.put("Transcription process completed successfully.")
        logging.info("Transcription process completed successfully.")

    except Exception as e:
        text_queue.put(f"Error during transcription: {str(e)}")
        logging.error(f"Error during transcription: {e}")

# Function to update the textbox from the queue for transcription
def update_transcription_textbox_from_queue(text_queue):
    try:
        while True:
            text = text_queue.get_nowait()
            update_textbox(text)
    except queue.Empty:
        pass
    if transcription_active:
        app.after(100, lambda: update_transcription_textbox_from_queue(text_queue))

# Function to start the transcription process
def start_transcription():
    global transcription_active
    global selected_date

    if transcription_active:
        update_textbox("Transcription is already in progress.")
        logging.warning("Attempted to start transcription while already active.")
        return

    if not selected_date:
        update_textbox("No date selected for transcription.")
        logging.error("No date selected for transcription.")
        return

    # Set transcription_active flag
    transcription_active = True
    logging.debug("Transcription process started.")
    update_textbox("Transcription process started.")

    # Set status light to green (running)
    update_status_light(RUNNING_COLOR)

    # Create a queue for capturing output
    text_queue = queue.Queue()

    # Start the transcription process in a separate thread
    transcription_thread = threading.Thread(target=run_transcription_process, args=(text_queue, selected_date), daemon=True)
    transcription_thread.start()
    logging.debug("Transcription thread started.")

    # Start updating the textbox from the queue
    update_transcription_textbox_from_queue(text_queue)

    # Reset transcription_active flag when thread finishes
    def check_thread():
        if not transcription_thread.is_alive():
            transcription_active = False
            update_status_light(IDLE_COLOR)
            logging.debug("Transcription process set to inactive.")
        else:
            app.after(100, check_thread)

    app.after(100, check_thread)
