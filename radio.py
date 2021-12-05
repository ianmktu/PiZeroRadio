import json
import os
import shlex
import signal
import ST7789
import subprocess
import sys
import threading
import time
import traceback

import RPi.GPIO as GPIO

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from datetime import date, datetime
from urllib.request import Request, urlopen

BUTTONS_BCM_VALUES = [5, 6, 16]
BUTTON_LETTER_TO_BCM_MAP = {'A':5, 'B':6, 'X':16}

stream_url = "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_one"

class RadioStreamThread:
    def __init__(self):
        self.thread = None
        self.started = True
        self.radio_stream_process = None
        self.args = ["cvlc", "--http-reconnect", "--play-and-exit", stream_url]

    def radio_stream(self):
        self.radio_stream_process = subprocess.Popen(self.args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(3)
        print(self.radio_stream_process)

    def run(self):
        self.thread = threading.Thread(target=self.radio_stream, args=())
        self.thread.start()

    def stop(self):
        if self.started:
            self.started = False
            if self.radio_stream_process is not None:
                self.radio_stream_process.kill()
            self.thread.join()


class DisplayThread:
    def __init__(self):
        self.thread = None
        self.started = True

    def display(self):
        disp = ST7789.ST7789(
            port=0,
            cs=ST7789.BG_SPI_CS_FRONT,
            dc=9,
            backlight=13,
            spi_speed_hz=2 * 1000 * 1000
        )
        disp.begin()

        WIDTH = disp.width
        HEIGHT = disp.height

        img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))

        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        push_down = 40

        while True:
            push_down = 40                    

            now = datetime.now()
            time_string = now.strftime("%H:%M:%S")
            draw.rectangle((0, 0, WIDTH, HEIGHT), (0, 0, 0))
            draw.text((24, 20 + push_down), time_string, font=font, fill=(255, 255, 255))

            today = date.today()
            day_string = today.strftime("%A")
            draw.text((24, 60 + push_down), day_string, font=font, fill=(255, 255, 255))

            date_string = today.strftime("%d %b %Y")
            draw.text((24, 100 + push_down), date_string, font=font, fill=(255, 255, 255))

            disp.display(img)


    def run(self):
        self.thread = threading.Thread(target=self.display, args=())
        self.thread.start()

    def stop(self):
        if self.started:
            self.started = False
            self.thread.join()

    def restart(self):
        self.stop()
        time.sleep(3)
        self.run()


def is_network_alive() -> bool:
    cmd = "ping -q -w 1 -c 1 www.google.co.uk"
    args = shlex.split(cmd)
    command_output = subprocess.call(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return command_output == 0


def main():
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTONS_BCM_VALUES, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        radio_stream_thread = RadioStreamThread()
        radio_stream_thread.run()

        display_thread = DisplayThread()
        display_thread.run()

        tick = -1
        while True:
            tick += 1

            if tick % 10 == 0:
                tick = 0
                run_once = True
                while not is_network_alive():
                    if run_once:
                        wlan_shutdown_args = ["sudo", "/sbin/ifconfig", "wlan0", "down"]
                        subprocess.call(wlan_shutdown_args, shell=True)
                        run_once = False

                    wlan_startup_args = ["sudo", "/sbin/ifconfig", "wlan0", "up"]
                    subprocess.call(wlan_startup_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                    if is_network_alive():
                        radio_stream_thread.stop()
                        radio_stream_thread = RadioStreamThread()
                        radio_stream_thread.run()
                        break

                # Restart if exited
                if radio_stream_thread.radio_stream_process is not None:
                    poll = radio_stream_thread.radio_stream_process.poll()
                    if poll is not None:
                        radio_stream_thread.stop()
                        radio_stream_thread = RadioStreamThread()
                        radio_stream_thread.run()

            input_state_a = GPIO.input(BUTTON_LETTER_TO_BCM_MAP['A'])
            if input_state_a == False:
                print('Volume Up')
                command = """amixer set Master 10%+"""
                subprocess.call(command, shell=True)
                time.sleep(0.2)

            input_state_b = GPIO.input(BUTTON_LETTER_TO_BCM_MAP['B'])
            if input_state_b == False:
                print('Volume Down')
                command = """amixer set Master 10%-"""
                subprocess.call(command, shell=True)
                time.sleep(0.2)

            input_state_x = GPIO.input(BUTTON_LETTER_TO_BCM_MAP['X'])
            if input_state_x == False:
                print('Restart Threads')
                radio_stream_thread.stop()
                radio_stream_thread = RadioStreamThread()
                radio_stream_thread.run()
                time.sleep(0.2)

            time.sleep(1)
    except Exception:
        traceback.print_exc()
    finally:
        GPIO.cleanup()
        radio_stream_thread.stop()
        sys.exit(0)


if __name__ == "__main__":
    while True:
        main()
