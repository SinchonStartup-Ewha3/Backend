import base64
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Post


User = get_user_model()
TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PostAPITests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(
            TEMP_MEDIA_ROOT,
            ignore_errors=True,
        )

    def setUp(self):
        self.author = User.objects.create_user(
            nickname="작성자",
        )

        self.other_user = User.objects.create_user(
            nickname="다른사용자",
        )

        self.create_url = reverse(
            "community:post-list-create"
        )

    def make_test_image(self):
        # 1×1 크기의 테스트용 PNG
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
            "CAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/x8AAusB9Y9Zl1sAAAAASUVORK5CYII="
        )

        return SimpleUploadedFile(
            name="test.png",
            content=png_data,
            content_type="image/png",
        )

    def test_login_is_required(self):
        response = self.client.post(
            self.create_url,
            {
                "content": "오늘 조금 추워요.",
                "tag": "cold",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_create_post_without_image(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "오늘 날씨가 좋아요.",
                "tag": "normal",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            Post.objects.count(),
            1,
        )

        post = Post.objects.get()

        self.assertEqual(
            post.user,
            # 빈칸 5: 게시글을 작성한 사용자
            self._____,
        )

        self.assertEqual(
            post.tag,
            "normal",
        )

        self.assertFalse(bool(post.image))

    def test_create_post_with_image(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "사진과 함께 등록합니다.",
                "tag": "hot",
                "image": self.make_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        post = Post.objects.get()
        self.assertTrue(bool(post.image))

    def test_invalid_tag_is_rejected(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "잘못된 태그입니다.",
                "tag": "rain",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "tag",
            response.data,
        )

    def test_empty_content_is_rejected(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "   ",
                "tag": "cold",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "content",
            response.data,
        )

    def test_author_can_update_post(self):
        post = Post.objects.create(
            user=self.author,
            content="수정 전 내용",
            tag=Post.Tag.COLD,
        )

        self.client.force_authenticate(
            user=self.author,
        )

        detail_url = reverse(
            "community:post-detail",
            kwargs={"post_id": post.pk},
        )

        response = self.client.patch(
            detail_url,
            {
                "content": "수정된 내용",
                "tag": "hot",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        post.refresh_from_db()

        self.assertEqual(
            post.content,
            "수정된 내용",
        )

        self.assertEqual(
            post.tag,
            "hot",
        )

    def test_other_user_cannot_update_post(self):
        post = Post.objects.create(
            user=self.author,
            content="작성자의 게시글",
            tag=Post.Tag.NORMAL,
        )

        self.client.force_authenticate(
            # 빈칸 6: 작성자가 아닌 다른 사용자
            user=self._____,
        )

        detail_url = reverse(
            "community:post-detail",
            kwargs={"post_id": post.pk},
        )

        response = self.client.patch(
            detail_url,
            {
                "content": "몰래 수정",
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        post.refresh_from_db()

        self.assertEqual(
            post.content,
            "작성자의 게시글",
        )