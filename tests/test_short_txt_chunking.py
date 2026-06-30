"""Regression: short .txt uploads must produce at least one chunk."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from backend.knowledge_base import chunk_and_add_document

SHORT_TXT = (
    "Assistify syscheck magic phrase ZEBRA-QUASAR-4242. "
    "Returns within 30 days."
)


def test_short_txt_generates_chunks():
    mock_collection = MagicMock()
    mock_collection.name = "test_short_txt"
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.array([[0.1] * 8])

    with patch("backend.knowledge_base.client") as mock_client, patch(
        "backend.knowledge_base.get_or_create_collection",
        return_value=mock_collection,
    ), patch("backend.knowledge_base.embedder", mock_embedder):
        mock_client.get_or_create_collection.return_value = mock_collection

        details = chunk_and_add_document(
            "short_txt_doc",
            SHORT_TXT,
            metadata={"file_ext": "txt"},
            return_details=True,
            target_collection_name="test_short_txt",
        )

    assert details["generated_chunks"] >= 1, details.get("reason")
    assert details["indexed_chunks"] >= 1, details.get("reason")
