"""Game packager — bundles generated HTML and uploads to MinIO."""

from app.services import storage_service


class GamePackager:
    """
    Packages a generated HTML game for distribution.

    Responsibilities:
    1. Optionally inline CDN scripts (download and embed)
    2. Inject asset references as data URIs if needed
    3. Upload the single HTML file to MinIO
    4. Return the public OSS URL
    """

    async def package_and_upload(
        self,
        game_id: str,
        html_code: str,
    ) -> str:
        """
        Upload the game HTML to MinIO and return the public URL.

        Args:
            game_id: UUID of the game
            html_code: The complete HTML code to upload

        Returns:
            Public MinIO URL for the playable game
        """
        # Upload to MinIO at games/{game_id}/index.html
        oss_url = await storage_service.upload_html(game_id, html_code)
        return oss_url
