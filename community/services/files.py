import logging

from django.db import transaction


logger = logging.getLogger(__name__)


def delete_storage_file_on_commit(*, storage, name):
    """DB 작업이 정상적으로 커밋된 후 저장소의 파일을 삭제한다."""

    if not name:
        return

    def delete_file():
        try:
            storage.delete(name)
        except Exception:
            logger.exception(
                "커뮤니티 이미지 삭제에 실패했습니다: %s",
                name,
            )

    transaction.on_commit(delete_file)
    