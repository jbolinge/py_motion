#! /usr/bin/python

import smtplib, multiprocessing
import datetime as dt
import imutils, time, json, warnings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import cv2
from picamera.array import PiRGBArray
from picamera import PiCamera

def run_motion(conf):
	#camera = cv2.VideoCapture(0)
	camera = PiCamera()
	camera.resolution = tuple(conf["resolution"])
	camera.framerate = conf["fps"]
	rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))
	#print "Warming up"
	time.sleep(conf["camera_warmup_time"])
	avg = None
	last_MMS = dt.datetime.now()
	last_save = dt.datetime.now()
	motion_counter = 0
	#while True:
	for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
		frame = f.array
		#(grabbed, frame) = camera.read()
		#if not grabbed:
		#	break

		timestamp = dt.datetime.now()
		text = "Unoccupied"

		frame = imutils.resize(frame, width=500)
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		gray = cv2.GaussianBlur(gray, (21, 21), 0)
		if avg is None:
			print "Starting background model"
			avg = gray.copy().astype("float")
			rawCapture.truncate(0)
			continue
		cv2.accumulateWeighted(gray, avg, 0.5)
		frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

		thresh = cv2.threshold(frameDelta, conf["delta_thresh"], 255, cv2.THRESH_BINARY)[1]
		thresh = cv2.dilate(thresh, None, iterations=2)
		(_, cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

		for c in cnts:
			if cv2.contourArea(c) < conf["min_area"]:
				continue
			(x, y, w, h) = cv2.boundingRect(c)
			cv2.rectangle(frame, (x,y), (x+w, y+h), (0, 255, 0), 2)
			text = "Occupied"
		ts = timestamp.strftime("%A %d %B %Y %H %M %S")
		#cv2.putText(frame, "Room Status: {}".format(text), (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
		cv2.putText(frame, ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
		if text == "Occupied":
			if (timestamp - last_save).seconds >= conf["min_save_seconds"]:
				motion_counter += 1
				if motion_counter >= conf["min_motion_frames"]:
					image_name = "{t_stamp}.jpg".format(t_stamp=ts)
					cv2.imwrite('images/' + image_name, frame)
					last_save = timestamp
					motion_counter = 0
					if (timestamp - last_MMS).seconds >= conf["min_upload_seconds"]:
						a = multiprocessing.Process(target=send_mms, args=(image_name, conf))
						a.start()
						last_MMS = timestamp
		else:
			motion_counter = 0
		if conf["show_video"]:
			cv2.imshow("Security Feed", frame)
			key = cv2.waitKey(1) & 0xFF
			if key == ord("q"):
				break
		rawCapture.truncate(0)

def send_mms(image_filename, conf):
	now = dt.datetime.now()
	now_txt = now.strftime('%B-%d-%Y %H:%M:%S')
	msg = MIMEMultipart()
	msg['To'] = conf["mms_to"]
	msg['From'] = conf["smtp_user"]
	msgText = MIMEText("Motion detected! %s" % now)
	msgText.set_charset("ISO-8859-1")
	msg.attach(msgText)
	with open('images/' + image_filename, 'rb') as f:
		attachment = MIMEImage(f.read())
	attachment.add_header('Content-Disposition','attachment',filename=image_filename)
	msg.attach(attachment)
	s = smtplib.SMTP(conf["smtp_server"], conf["smtp_port"])
	s.ehlo()
	s.starttls()
	s.ehlo()
	s.login(conf["smtp_user"], conf["smtp_pass"])
	s.sendmail(conf["smtp_user"], conf["mms_to"].split(","), msg.as_string())
	s.quit()

if __name__=='__main__':
	warnings.filterwarnings("ignore")
	with open("conf.json", 'r') as f:
		conf = json.load(f)
	run_motion(conf)
