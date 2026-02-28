import argparse
import json
import time

import rclpy

from .booster_rpc import BoosterRpcClient


def _print_response(response) -> None:
    print(f"status={response.msg.status}")
    body = response.msg.body or ""
    if not body:
        print("body=")
        return
    try:
        print(json.dumps(json.loads(body), indent=2, sort_keys=True))
    except json.JSONDecodeError:
        print(f"body={body}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for Booster K1 RPC control")
    parser.add_argument("--service", default="booster_rpc_service", help="ROS2 RPC service name")
    parser.add_argument("--timeout", type=float, default=5.0, help="RPC timeout seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    move = sub.add_parser("move", help="Send move command")
    move.add_argument("--vx", type=float, required=True)
    move.add_argument("--vy", type=float, default=0.0)
    move.add_argument("--vyaw", type=float, default=0.0)
    move.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="If >0, wait this many seconds and then send stop automatically",
    )

    sub.add_parser("stop", help="Stop locomotion")

    hand = sub.add_parser("hand-ee", help="Toggle hand end-effector control")
    hand.add_argument("--on", action="store_true", help="Enable mode")
    hand.add_argument("--off", action="store_true", help="Disable mode")

    raw = sub.add_parser("raw", help="Call arbitrary API id with JSON body")
    raw.add_argument("--api-id", type=int, required=True)
    raw.add_argument(
        "--body",
        default="{}",
        help='JSON object string body. Example: --body "{\"vx\":0.2,\"vy\":0,\"vyaw\":0}"',
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "hand-ee" and args.on == args.off:
        parser.error("hand-ee requires exactly one of --on or --off")

    try:
        raw_body = None
        if args.command == "raw":
            raw_body = json.loads(args.body)
            if not isinstance(raw_body, dict):
                raise ValueError("--body must parse to a JSON object")
    except Exception as exc:
        parser.error(str(exc))

    rclpy.init()
    node = BoosterRpcClient(service_name=args.service)

    try:
        if not node.wait_for_service(timeout_sec=args.timeout):
            print(f"Service '{args.service}' is not available")
            return 2

        if args.command == "move":
            response = node.move(args.vx, args.vy, args.vyaw, timeout_sec=args.timeout)
            _print_response(response)
            if args.duration > 0:
                time.sleep(args.duration)
                print("auto-stop...")
                response = node.stop(timeout_sec=args.timeout)
                _print_response(response)

        elif args.command == "stop":
            response = node.stop(timeout_sec=args.timeout)
            _print_response(response)

        elif args.command == "hand-ee":
            response = node.switch_hand_end_effector_control(args.on, timeout_sec=args.timeout)
            _print_response(response)

        elif args.command == "raw":
            response = node.call_api(args.api_id, raw_body, timeout_sec=args.timeout)
            _print_response(response)

    finally:
        node.destroy_node()
        rclpy.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
