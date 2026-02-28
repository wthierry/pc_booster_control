import json
from typing import Any

import rclpy
from rclpy.node import Node

from booster_interface.msg import BoosterApiReqMsg
from booster_interface.srv import RpcService


DEFAULT_SERVICE_NAME = "booster_rpc_service"
DEFAULT_MOVE_API_ID = 2001
DEFAULT_SWITCH_HAND_EE_API_ID = 2012


class BoosterRpcClient(Node):
    def __init__(self, service_name: str = DEFAULT_SERVICE_NAME) -> None:
        super().__init__("pc_booster_control_rpc_client")
        self._client = self.create_client(RpcService, service_name)

    def wait_for_service(self, timeout_sec: float = 5.0) -> bool:
        return self._client.wait_for_service(timeout_sec=timeout_sec)

    def call_api(
        self,
        api_id: int,
        body: dict[str, Any] | None = None,
        timeout_sec: float = 5.0,
    ) -> RpcService.Response:
        req_msg = BoosterApiReqMsg()
        req_msg.api_id = int(api_id)
        req_msg.body = json.dumps(body) if body is not None else ""

        request = RpcService.Request()
        request.msg = req_msg

        future = self._client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)

        if not future.done() or future.result() is None:
            raise TimeoutError(f"RPC call timed out or failed for api_id={api_id}")

        return future.result()

    def move(self, vx: float, vy: float, vyaw: float, timeout_sec: float = 5.0) -> RpcService.Response:
        return self.call_api(
            DEFAULT_MOVE_API_ID,
            {"vx": float(vx), "vy": float(vy), "vyaw": float(vyaw)},
            timeout_sec=timeout_sec,
        )

    def stop(self, timeout_sec: float = 5.0) -> RpcService.Response:
        return self.move(0.0, 0.0, 0.0, timeout_sec=timeout_sec)

    def switch_hand_end_effector_control(self, switch_on: bool, timeout_sec: float = 5.0) -> RpcService.Response:
        return self.call_api(
            DEFAULT_SWITCH_HAND_EE_API_ID,
            {"switch_on": bool(switch_on)},
            timeout_sec=timeout_sec,
        )
