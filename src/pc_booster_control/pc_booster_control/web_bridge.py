import threading

import cv2
import numpy as np
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class RosWebBridge(Node):
    def __init__(self, color_topic: str, depth_topic: str) -> None:
        super().__init__("pc_booster_control_web_bridge")
        self._lock = threading.Lock()
        self._frames: dict[str, bytes] = {}

        self.create_subscription(Image, color_topic, self._on_color, qos_profile_sensor_data)
        self.create_subscription(Image, depth_topic, self._on_depth, qos_profile_sensor_data)

    def _on_color(self, msg: Image) -> None:
        frame = self._decode_color(msg)
        if frame is None:
            return
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        with self._lock:
            self._frames["color"] = encoded.tobytes()

    def _on_depth(self, msg: Image) -> None:
        depth = self._decode_depth(msg)
        if depth is None:
            return
        depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        ok, encoded = cv2.imencode(".jpg", depth_color, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        with self._lock:
            self._frames["depth"] = encoded.tobytes()

    def get_frame_jpeg(self, stream: str) -> bytes | None:
        with self._lock:
            return self._frames.get(stream)

    @staticmethod
    def _decode_color(msg: Image) -> np.ndarray | None:
        width = int(msg.width)
        height = int(msg.height)
        data = np.frombuffer(msg.data, dtype=np.uint8)
        encoding = (msg.encoding or "").lower()

        if encoding in ("nv12", "") and data.size == width * height * 3 // 2:
            yuv = data.reshape((height * 3 // 2, width))
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)

        if encoding in ("rgb8",) and data.size == width * height * 3:
            rgb = data.reshape((height, width, 3))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        if encoding in ("bgr8",) and data.size == width * height * 3:
            return data.reshape((height, width, 3))

        return None

    @staticmethod
    def _decode_depth(msg: Image) -> np.ndarray | None:
        width = int(msg.width)
        height = int(msg.height)
        data = np.frombuffer(msg.data, dtype=np.uint8)

        if data.size == width * height * 2:
            return data.view(np.uint16).reshape((height, width))

        if data.size == width * height * 4:
            return data.view(np.float32).reshape((height, width))

        return None
