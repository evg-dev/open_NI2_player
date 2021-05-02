#! /usr/bin/python3
# Testing on OpenNI-Linux-x64-2.3
import cv2
import sys
import numpy as np

from PyQt5.QtWidgets import QLabel, QApplication, QAction, QSlider, QFileDialog, QMainWindow, QPushButton, qApp
from PyQt5.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from openni.openni2 import PlaybackSupport
from PyQt5.QtGui import QPixmap, QImage
from openni import openni2


class Slider(QSlider):
    slider_clicked = pyqtSignal(int)

    def mouseReleaseEvent(self, e):

        if e.button() == Qt.LeftButton:

            e.accept()
            x = e.pos().x()
            value = (self.maximum() - self.minimum()) * x / self.width() + self.minimum()
            self.slider_clicked.emit(int(round(value)))
        else:
            return super().mouseReleaseEvent(self, e)


class Thread(QThread):
    COLOR_STREAM = 0
    DEPTH_STREAM = 1
    DEFAULT_SPEED = 1.0
    DEPTH_SPEED = 0.33
    PATH_TO_OpenNI_LIB = '.OpenNI-Linux-x64-2.3/Redist'

    change_pixmap = pyqtSignal(QImage)
    number_of_frames = 0
    is_running = True
    counter = 0

    current_stream = None
    file = None
    ps = None  # PlaybackSupport
    stream_type = COLOR_STREAM

    def stream(self):

        if self.file:
            openni2.initialize(self.PATH_TO_OpenNI_LIB)
            dev = openni2.Device.open_file(self.file.encode('utf-8'))
            self.ps = PlaybackSupport(dev)

            if self.stream_type == self.COLOR_STREAM:
                self.current_stream = dev.create_color_stream()
            else:
                self.current_stream = dev.create_depth_stream()

            self.number_of_frames = self.current_stream.get_number_of_frames()

            if self.stream_type == self.COLOR_STREAM:
                self.number_of_frames -= 1

            self.current_stream.start()
            # Loop
            while self.is_running & (self.counter <= self.number_of_frames) and self.isRunning():
                # Crash here on big file without this
                try:
                    self.ps.seek(self.current_stream, self.counter)
                except Exception as e:
                    print(e)

                # Put the depth frame into a numpy array and reshape it
                frame = self.current_stream.read_frame()

                if self.stream_type == self.COLOR_STREAM:
                    self.ps.set_speed(self.DEFAULT_SPEED)
                    frame_data = self.color_stream(frame)
                else:
                    self.ps.set_speed(self.DEPTH_SPEED)
                    frame_data = self.depth_stream(frame)

                self.counter += 1
                return frame_data

    def run(self, manual=False):

        if manual and not self.isRunning() and self.file:

            self.ps.seek(self.current_stream, self.counter)

            frame = self.current_stream.read_frame()

            if self.stream_type == self.COLOR_STREAM:
                self.ps.set_speed(self.DEFAULT_SPEED)
                frame = self.color_stream(frame)
            else:
                self.ps.set_speed(self.DEPTH_SPEED)
                frame = self.depth_stream(frame)

            if self.stream_type == self.DEPTH_STREAM:
                frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

            self.format_to_qt(frame)

        elif self.file and self.isRunning():

            while self.is_running & (self.counter <= self.number_of_frames):

                try:
                    frame = self.stream()

                    if self.stream_type == self.DEPTH_STREAM:
                        frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

                    self.format_to_qt(frame)

                except Exception as e:
                    print(e)

    def format_to_qt(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytesPerLine = ch * w
        convertToQtFormat = QImage(rgb_image.data, w, h, bytesPerLine, QImage.Format_RGB888)
        p = convertToQtFormat.scaled(640, 480, Qt.KeepAspectRatio)
        self.change_pixmap.emit(p)

    @staticmethod
    def color_stream(frame):
        frame_data = np.array(frame.get_buffer_as_triplet()).reshape([480, 640, 3])
        R = frame_data[:, :, 0]
        G = frame_data[:, :, 1]
        B = frame_data[:, :, 2]
        return np.transpose(np.array([B, G, R]), [1, 2, 0])

    @staticmethod
    def depth_stream(frame):
        refPt = []

        frame_data = frame.get_buffer_as_uint16()

        # Put the depth frame into a numpy array and reshape it
        img = np.frombuffer(frame_data, dtype=np.uint16)
        img.shape = (1, 480, 640)

        img = np.concatenate((img, img, img), axis=0)
        img = np.swapaxes(img, 0, 2)
        img = np.swapaxes(img, 0, 1)

        if len(refPt) > 1:
            img = img.copy()
            cv2.rectangle(img, refPt[0], refPt[1], (0, 255, 0), 2)
        return img


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        self.get_status_bar()
        self.setGeometry(300, 300, 640, 540)
        # create a label
        self.label = QLabel(self)
        self.label.move(0, 20)
        self.label.resize(640, 480)

        self.th = Thread(self)
        self.th.change_pixmap.connect(self.set_image)
        self.th.start()

        self.button_play = QPushButton('Pause', self)
        self.button_play.move(590, 500)
        self.button_play.resize(50, 40)
        self.button_play.clicked.connect(self.stop_video)

        self.button_play = QPushButton('Play', self)
        self.button_play.move(540, 500)
        self.button_play.resize(50, 40)
        self.button_play.clicked.connect(self.play_video)

        self.button_play = QPushButton('>>', self)
        self.button_play.move(515, 500)
        self.button_play.resize(25, 40)
        self.button_play.clicked.connect(self.next_frame)

        self.button_play = QPushButton('<<', self)
        self.button_play.move(490, 500)
        self.button_play.resize(25, 40)
        self.button_play.clicked.connect(self.previous_frame)

        self.sld = Slider(Qt.Horizontal, self)
        self.sld.setFocusPolicy(Qt.NoFocus)
        self.sld.move(10, 500)
        self.sld.resize(460, 40)
        self.sld.slider_clicked.connect(self.set_slider_manual)

        self.show()

    def set_slider_manual(self, value):
        self.stop_video()

        if value < 0:
            value = 0

        frame_index = self.th.number_of_frames * value / 100
        self.th.counter = int(round(frame_index))
        self.th.run(True)

    @pyqtSlot(QImage)
    def set_image(self, image):
        self.set_slider()
        self.label.setPixmap(QPixmap.fromImage(image))

    def set_slider(self):
        value = self.th.counter / self.th.number_of_frames * 100
        self.sld.setSliderPosition(int(round(value)))

    def get_status_bar(self):
        self.statusBar()
        menubar = self.menuBar()
        file_menu = menubar.addMenu('&File')
        settings = menubar.addMenu('&Settings')

        color_stream_action = QAction('COLOR STREAM', self)
        color_stream_action.triggered.connect(self.color_stream)

        depth_stream_action = QAction('DEPTH STREAM', self)
        depth_stream_action.triggered.connect(self.depth_stream)

        settings.addAction(color_stream_action)
        settings.addAction(depth_stream_action)

        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)

        close_action = QAction('Exit', self)
        close_action.setShortcut('Ctrl+Q')
        close_action.triggered.connect(qApp.quit)

        file_menu.addAction(open_action)
        file_menu.addAction(close_action)

    def color_stream(self):
        self.stop_video()
        # No refresh
        # self.th.counter = 0
        # self.th.number_of_frames = 0
        self.th.stream_type = self.th.COLOR_STREAM
        self.play_video()

    def depth_stream(self):
        self.stop_video()
        # No refresh
        # self.th.counter = 0
        # self.th.number_of_frames = 0
        self.th.stream_type = self.th.DEPTH_STREAM
        self.play_video()

    def open_file(self):
        self.stop_video()
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, "OpenNI file", "",
                                                   "OpenNI files (*.oni)", options=options)
        if file_name:
            self.th.file = file_name
            self.th.number_of_frames = 0
            self.th.counter = 0
            self.play_video()

    def play_video(self):
        self.th.is_running = True
        if not self.th.isRunning():
            self.th.start()

    def stop_video(self):
        self.th.is_running = False

    def next_frame(self):
        self.stop_video()
        if self.th.counter < self.th.number_of_frames:
            self.th.counter += 1
            self.th.run(True)

    def previous_frame(self):
        self.stop_video()
        if self.th.counter >= 1:
            self.th.counter -= 1
            self.th.run(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    display_image_widget = MainWindow()
    display_image_widget.show()
    sys.exit(app.exec_())
