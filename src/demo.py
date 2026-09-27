import os

from notification_service import BuildEvent, InfraiClient, NotificationService


def main() -> None:
    client = InfraiClient(os.environ["INFRAI_API_KEY"])
    service = NotificationService(client)
    result = service.record_release(BuildEvent("build-1042", "acme/cli", "passed", "abc1234"))
    print(f"queued {result.notification_id}: {result.message}")


if __name__ == "__main__":
    main()
