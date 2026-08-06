from django.urls import path

from .views import (
    BookkeepingOverviewView,
    MatchingRuleDeleteView,
    MatchingRuleEditView,
    MatchingRuleListView,
)


urlpatterns = [
    path('', BookkeepingOverviewView.as_view(), name='bookkeeping_overview'),
    path(
        'matching-rules/',
        MatchingRuleListView.as_view(),
        name='matching_rule_list',
    ),
    path(
        'matching-rules/<uuid:pk>/edit/',
        MatchingRuleEditView.as_view(),
        name='matching_rule_edit',
    ),
    path(
        'matching-rules/<uuid:pk>/delete/',
        MatchingRuleDeleteView.as_view(),
        name='matching_rule_delete',
    ),
]
