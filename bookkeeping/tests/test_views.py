from django.test import TestCase
from django.urls import reverse

from bookkeeping.models import Mandant


class BookkeepingViewTests(TestCase):
    def setUp(self):
        self.mandant = Mandant.objects.create(name="Test KG", kurzname="TEST")

    def test_dashboard_is_anonymously_accessible_and_uses_own_base_template(self):
        response = self.client.get(reverse("bookkeeping:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookkeeping/base.html")
        self.assertContains(response, "/static/bookkeeping/css/styles.css")
        self.assertNotContains(response, "/static/webapp/")

    def test_root_dashboard_remains_the_webapp_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "webapp/home.html")

    def test_master_data_route_is_namespaced(self):
        response = self.client.get(reverse("bookkeeping:stammdaten"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("bookkeeping:bankkonto_list"))
