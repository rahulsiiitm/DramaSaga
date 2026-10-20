"""MediaPipe single-face geometry tracking, not identity or phoneme validation."""
import math
from pathlib import Path
from .core import digest


def mouth_geometry(landmarks):
    def distance(a,b):
        x,y=landmarks[a],landmarks[b]
        return math.hypot(x.x-y.x,x.y-y.y)
    width=distance(61,291)
    if width<=1e-6:raise ValueError('Degenerate mouth landmarks')
    return distance(13,14)/width


def track_mouth(video,audio,model_path,speaker_id,step_seconds=.04,max_seconds=180):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    if step_seconds!=.04:raise ValueError('Tracker requires 25 Hz sampling')
    if not speaker_id or not Path(model_path).is_file():raise ValueError('Named speaker and installed task model required')
    cap=cv2.VideoCapture(str(video))
    try:
        fps=cap.get(cv2.CAP_PROP_FPS);count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not fps or not count or not 0<count/fps<=max_seconds:raise ValueError('Invalid or excessive video duration')
        options=vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,num_faces=2,min_face_detection_confidence=.95,
            min_face_presence_confidence=.95,min_tracking_confidence=.95)
        samples=[];i=0;next_t=0
        with vision.FaceLandmarker.create_from_options(options) as tracker:
            while True:
                ok,frame=cap.read()
                if not ok:break
                seconds=i/fps;i+=1
                if seconds+1e-6<next_t:continue
                if abs(seconds-next_t)>.021:raise ValueError('Video frame rate too low for 25 Hz tracking')
                image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                result=tracker.detect_for_video(image,round(seconds*1000))
                if len(result.face_landmarks)!=1:raise ValueError('Missing/ambiguous face: no speaker track')
                samples.append({'seconds':round(next_t,6),'mouth_open':mouth_geometry(result.face_landmarks[0]),
                    'visible_speakers':1,'tracking_threshold':.95,'confidence':None})
                next_t=round(next_t+step_seconds,6)
        if len(samples)<25:raise ValueError('Track shorter than one second')
        return {'video_sha256':digest(video),'audio_sha256':digest(audio),'model_sha256':digest(model_path),
            'engine':'mediapipe-face-landmarker-'+mp.__version__,'speaker_id':speaker_id,'identity_verified':False,
            'samples':samples,'status':'geometry_only_no_calibrated_confidence_or_speaker_identity'}
    finally:cap.release()
