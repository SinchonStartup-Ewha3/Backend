import base64
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Region

from .models import Post, PostLike


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
        self.region = Region.objects.create(
            region_code="1114055000",
            region_name="서울특별시 중구 소공동",
            lat="37.563800",
            lng="126.979500",
            grid_nx=60,
            grid_ny=127,
        )

        self.author = User.objects.create_user(
            nickname="작성자",
            region=self.region,
        )

        self.other_user = User.objects.create_user(
            nickname="다른사용자",
            region=self.region,
        )

        self.create_url = reverse(
            "community:post-list-create"
        )

    def make_test_image(self):
        # 1×1 크기의 테스트용 PNG
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
            "CAIAAACQd1PeAAAADElEQVR4nGP4"
            "//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
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
                "content": "가디건",
                "tag": "cardigan",
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
                "content": "패당",
                "tag": "padded",
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
            self.author
        )

        self.assertEqual(
            post.tag,
            "padded",
        )

        self.assertEqual(
            post.region,
            self.region,
        )

        self.assertFalse(bool(post.image))

    def test_create_post_with_image(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "코트",
                "tag": "coat",
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
                "tag": "shoes",
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

    def test_tag_is_required(self):
        # [기능] 게시물 작성 시 태그를 반드시 선택해야 한다.
        self.client.force_authenticate(user=self.author)

        response = self.client.post(
            self.create_url,
            {"content": "태그가 없는 게시물"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tag", response.data)
        self.assertEqual(Post.objects.count(), 0)

    def test_empty_content_is_rejected(self):
        self.client.force_authenticate(
            user=self.author,
        )

        response = self.client.post(
            self.create_url,
            {
                "content": "   ",
                "tag": "coat",
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
            tag=Post.Tag.CARDIGAN
        )

        self.client.force_authenticate(
            user=self.author,
        )

        detail_url = reverse(
            "community:post-update",
            kwargs={"post_id": post.pk},
        )

        response = self.client.patch(
            detail_url,
            {
                "content": "수정된 내용",
                "tag": "padded",
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
            "padded",
        )

    def test_other_user_cannot_update_post(self):
        post = Post.objects.create(
            user=self.author,
            content="작성자의 게시글",
            tag=Post.Tag.PADDED,
        )

        self.client.force_authenticate(
            user=self.other_user,
        )

        detail_url = reverse(
            "community:post-update",
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
            status.HTTP_404_NOT_FOUND,
        )

        post.refresh_from_db()

        self.assertEqual(
            post.content,
            "작성자의 게시글",
        )

    def test_author_can_delete_post(self):
        post = Post.objects.create(
            user=self.author,
            region=self.region,
            content="삭제할 게시물",
            tag=Post.Tag.COAT,
        )
        self.client.force_authenticate(user=self.author)

        response = self.client.delete(
            reverse(
                "community:post-update",
                kwargs={"post_id": post.pk},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Post.objects.filter(pk=post.pk).exists()
        )

    def test_other_user_cannot_delete_post(self):
        post = Post.objects.create(
            user=self.author,
            region=self.region,
            content="작성자의 게시물",
            tag=Post.Tag.COAT,
        )
        self.client.force_authenticate(user=self.other_user)

        response = self.client.delete(
            reverse(
                "community:post-update",
                kwargs={"post_id": post.pk},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(
            Post.objects.filter(pk=post.pk).exists()
        )

    def test_feed_requires_tag(self):
        # [기능] 피드 화면에서도 세 태그 중 하나를 선택해야 한다.
        self.client.force_authenticate(user=self.author)

        response = self.client.get(self.create_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tag", response.data)

    def test_feed_filters_posts_by_tag(self):
        # [기능] 선택한 태그에 해당하는 게시물만 피드에 표시한다.
        Post.objects.create(
            user=self.author,
            content="가디건 게시물",
            tag=Post.Tag.CARDIGAN,
        )
        Post.objects.create(
            user=self.author,
            content="코트 게시물",
            tag=Post.Tag.COAT,
        )
        self.client.force_authenticate(user=self.author)

        response = self.client.get(self.create_url, {"tag": "cardigan"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["tag"], "cardigan")
        self.assertEqual(response.data["results"][0]["tagLabel"], "가디건")
        self.assertIn("createdAtDisplay", response.data["results"][0])
        self.assertEqual(response.data["results"][0]["likeCount"], 0)
        self.assertFalse(response.data["results"][0]["isLiked"])
        self.assertNotIn("author", response.data["results"][0])
        self.assertNotIn("authorProfileImage", response.data["results"][0])

    def test_feed_rejects_invalid_tag(self):
        # [기능] 정의되지 않은 태그로는 피드를 조회할 수 없다.
        self.client.force_authenticate(user=self.author)

        response = self.client.get(self.create_url, {"tag": "shoes"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tag", response.data)

    def test_post_detail_can_be_retrieved(self):
        post = Post.objects.create(
            user=self.author,
            region=self.region,
            content="상세 조회할 게시물",
            tag=Post.Tag.PADDED,
        )
        self.client.force_authenticate(user=self.author)
        detail_url = reverse(
            "community:post-update",
            kwargs={"post_id": post.pk},
        )

        response = self.client.get(detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(response.data["postId"], post.pk)
        self.assertEqual(
            response.data["content"],
            "상세 조회할 게시물",
        )

    def test_other_user_cannot_retrieve_post_detail(self):
        post = Post.objects.create(
            user=self.author,
            region=self.region,
            content="작성자만 볼 상세 게시물",
            tag=Post.Tag.PADDED,
        )
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(
            reverse(
                "community:post-update",
                kwargs={"post_id": post.pk},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_my_post_list_only_contains_my_posts(self):
        my_post = Post.objects.create(
            user=self.author,
            region=self.region,
            content="내가 작성한 게시물",
            tag=Post.Tag.CARDIGAN,
        )
        Post.objects.create(
            user=self.other_user,
            region=self.region,
            content="다른 사용자의 게시물",
            tag=Post.Tag.CARDIGAN,
        )
        self.client.force_authenticate(user=self.author)

        response = self.client.get(
            reverse("community:my-post-list")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["postId"],
            my_post.pk,
        )

    def test_liked_post_list_only_contains_liked_posts(self):
        liked_post = Post.objects.create(
            user=self.other_user,
            region=self.region,
            content="공감한 게시물",
            tag=Post.Tag.PADDED,
        )
        Post.objects.create(
            user=self.other_user,
            region=self.region,
            content="공감하지 않은 게시물",
            tag=Post.Tag.PADDED,
        )
        PostLike.objects.create(
            user=self.author,
            post=liked_post,
        )
        self.client.force_authenticate(user=self.author)

        response = self.client.get(
            reverse("community:liked-post-list")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["postId"],
            liked_post.pk,
        )
        self.assertTrue(
            response.data["results"][0]["isLiked"]
        )

    def test_user_can_toggle_post_like(self):
        # [기능] 첫 클릭은 좋아요, 두 번째 클릭은 좋아요 취소
        post = Post.objects.create(
            user=self.author,
            content="좋아요 테스트 게시물",
            tag=Post.Tag.COAT,
        )
        self.client.force_authenticate(user=self.other_user)
        like_url = reverse(
            "community:post-like-toggle",
            kwargs={"post_id": post.pk},
        )

        like_response = self.client.post(like_url)

        self.assertEqual(like_response.status_code, status.HTTP_200_OK)
        self.assertTrue(like_response.data["isLiked"])
        self.assertEqual(like_response.data["likeCount"], 1)
        self.assertTrue(
            PostLike.objects.filter(post=post, user=self.other_user).exists()
        )

        unlike_response = self.client.post(like_url)

        self.assertEqual(unlike_response.status_code, status.HTTP_200_OK)
        self.assertFalse(unlike_response.data["isLiked"])
        self.assertEqual(unlike_response.data["likeCount"], 0)
        self.assertFalse(
            PostLike.objects.filter(post=post, user=self.other_user).exists()
        )

    def test_feed_shows_like_count_and_current_user_state(self):
        # [기능] 피드에 좋아요 수와 로그인 사용자의 좋아요 여부 표시
        post = Post.objects.create(
            user=self.author,
            content="좋아요가 있는 게시물",
            tag=Post.Tag.PADDED,
        )
        PostLike.objects.create(post=post, user=self.other_user)
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(self.create_url, {"tag": "padded"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        feed_post = response.data["results"][0]
        self.assertEqual(feed_post["likeCount"], 1)
        self.assertTrue(feed_post["isLiked"])
