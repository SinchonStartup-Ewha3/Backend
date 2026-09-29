from django.conf import settings
from django.db import models


class Post(models.Model):
    class Tag(models.TextChoices):
        CARDIGAN = "cardigan", "가디건"
        PADDED = "padded", "패딩"
        COAT = "coat", "코트"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_posts",
    )

    content = models.CharField(
    max_length=200,
    )

    
    tag = models.CharField(
        max_length=10,
        choices=Tag.choices,
    )

    
    image = models.ImageField(
        upload_to="community/posts/%Y/%m/%d/",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.content[:20]}"