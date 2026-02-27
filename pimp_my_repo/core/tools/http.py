"""HTTP operations controller for boosts."""

import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class HttpController:
    """Controller for HTTP operations in boosts."""

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> str:
        """Make an HTTP GET request and return the response body as a string.

        Args:
            url: The URL to request
            headers: Optional headers to include in the request
            timeout: Request timeout in seconds

        Returns:
            The response body as a decoded string

        Raises:
            urllib.error.URLError: If the request fails
            urllib.error.HTTPError: If the server returns an error status
            OSError: For network or other I/O errors

        """
        request = urllib.request.Request(url)  # noqa: S310
        if headers:
            for key, value in headers.items():
                request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8")  # type: ignore[no-any-return]
