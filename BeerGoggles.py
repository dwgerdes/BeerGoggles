#!/usr/bin/env python

from __future__ import division

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import cv2
import time
import os.path
import json
import argparse
from scipy.signal import find_peaks_cwt
from time import strftime
import requests
import threading
from threading import Thread, Event, ThreadError

class BubbleFinder(object):
	def __init__(self, config):
		self.config = config
		self.threshold = self.config["delta_thresh"]
		self.min_motion_frames = self.config["min_motion_frames"]
		self.max_motion_frames = self.config["max_motion_frames"]
		self.outfile = self.config["outfile"]

	def imgdiff(self, img1, img2):
		# smooth the images
	 	img1 = cv2.GaussianBlur(img1, (21, 21), 0)
	 	img2 = cv2.GaussianBlur(img2, (21, 21), 0)
	 	# take absolute difference, |img1-img2|
	 	frameDelta = cv2.absdiff(img1, img2)
	 	# perform thresholding
	 	thresh = cv2.threshold(frameDelta, self.threshold, 255, cv2.THRESH_BINARY)[1]
	    # dilate the thresholded image to fill in holes
	 	thresh = cv2.dilate(thresh, None, iterations=2)
	    # return pixel count above threshold in difference image
	 	return np.sum(thresh)/255

	def get_peaks(self, sequence, min_motion_frames=4, max_motion_frames=6):
		# look for features several frames in duration
		return find_peaks_cwt(sequence, np.arange(min_motion_frames, max_motion_frames+1))

	def process_buffer(self, buff, outfile='bubbles.csv'):
		features = self.get_peaks(buff['diff'].values, min_motion_frames=self.min_motion_frames, 
			max_motion_frames=self.max_motion_frames)
		df_bubbles = buff.iloc[features]
		df_bubbles.to_csv('bubbles.csv',mode='a', header=(not os.path.isfile(outfile)), index=False)

class Cam(object):

    def __init__(self, url, bubbler, user=None, password=None, upload_interval_seconds=60):

        self.user=user
        self.password=password
        self.bubbler=bubbler
        self.upload_interval_seconds = upload_interval_seconds
        if user is not None and password is not None:
            self.stream = requests.get(url, auth=(self.user,self.password), stream=True)
        else:
            self.stream = requests.get(url, stream=True)
        self.thread_cancelled = False
        self.thread = Thread(target=self.run)
        print "camera initialized"

    def start(self):
        self.thread.start()
        print "camera stream started"
    
    def run(self):
        bytes=''
        polling_start = time.time()
        prev_img = None
        diff_df = pd.DataFrame()
        while not self.thread_cancelled:
            try:
                cur_time = time.time()
                if cur_time - polling_start > self.upload_interval_seconds:
                    polling_start = cur_time
                    self.bubbler.process_buffer(diff_df)
                    diff_df = pd.DataFrame()
                bytes+=self.stream.raw.read(1024)
                a = bytes.find('\xff\xd8')
                b = bytes.find('\xff\xd9')
                if a!=-1 and b!=-1:
                    jpg = bytes[a:b+2]
                    bytes= bytes[b+2:]
                    img = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
                    if prev_img is not None:
                        diff = self.bubbler.imgdiff(img, prev_img)
                        diff_df = diff_df.append(pd.Series({'t':time.time(), 'ctime':time.ctime(), 
                                                            'diff':diff}), ignore_index=True)
                    prev_img = img
            except ThreadError:
                print 'Caught thread error...'
                self.thread_cancelled = True
        
        
    def is_running(self):
        return self.thread.isAlive()
      
    
    def shut_down(self):
        self.thread_cancelled = True
        print 'Shutting down'
        #block while waiting for thread to terminate
        while self.thread.isAlive():
            time.sleep(100)
        return True

def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("-c", "--conf", required=True, help="path to the JSON configuration file")
	args = vars(ap.parse_args())
	conf = json.load(open(args["conf"]))
	bubbler = BubbleFinder(conf)
	url = conf["url"]
	upload_interval = conf["upload_interval_seconds"]
	try:
		user, password=conf["user"], conf["password"]
	except KeyError:
		user, password = None, None
	cam = Cam(url, bubbler, user=user, password=password, upload_interval_seconds=upload_interval)

	cam.start()

if __name__ == '__main__':
	main()