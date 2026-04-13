from __future__ import annotations

import re

from mkdocs.plugins import BasePlugin


class SocialOverridePlugin(BasePlugin):
    def on_page_context(self, context, page, config, **kwargs):
        if page.meta and "image" in page.meta:
            page.custom_image = page.meta["image"]
        return context

    def on_post_page(self, html, page, config, **kwargs):
        if not hasattr(page, "custom_image"):
            return html

        site_url = (config.get("site_url") or "").rstrip("/")
        image_path = "/" + str(page.custom_image).lstrip("/")
        full_image_url = site_url + image_path

        og_tags = re.findall(r'<meta\\s+property="og:image"[^>]*?>', html)
        for tag in og_tags:
            if "/assets/images/social/" in tag:
                html = html.replace(tag, f'<meta property="og:image" content="{full_image_url}">')

        twitter_tags = re.findall(r'<meta\\s+name="twitter:image"[^>]*?>', html)
        for tag in twitter_tags:
            if "/assets/images/social/" in tag:
                html = html.replace(tag, f'<meta name="twitter:image" content="{full_image_url}">')

        return html

