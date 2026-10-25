from django.test import SimpleTestCase

from .settings import _get_allowed_hosts


class AllowedHostsTests(SimpleTestCase):
    def test_render_hostname_is_allowed_alongside_configured_hosts(self):
        hosts = _get_allowed_hosts(
            {
                "DJANGO_ALLOWED_HOSTS": "example.com, www.example.com",
                "RENDER_EXTERNAL_HOSTNAME": "status-2-dv6a.onrender.com",
            }
        )

        self.assertEqual(
            hosts,
            ["example.com", "www.example.com", "status-2-dv6a.onrender.com"],
        )

    def test_render_hostname_is_not_added_twice(self):
        hosts = _get_allowed_hosts(
            {
                "DJANGO_ALLOWED_HOSTS": "status-2-dv6a.onrender.com",
                "RENDER_EXTERNAL_HOSTNAME": "status-2-dv6a.onrender.com",
            }
        )

        self.assertEqual(hosts, ["status-2-dv6a.onrender.com"])
