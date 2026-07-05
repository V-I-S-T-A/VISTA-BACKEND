import uuid
from django.db import models


class Category(models.Model):
    category_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)

    class Meta:
        db_table = "tbl_Category"
        ordering = ["name"]

    def __str__(self):
        return self.name
        