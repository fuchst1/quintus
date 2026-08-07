from django.urls import path

from .views import (
    BankTransactionNoteView,
    BookingEntryView,
    BookkeepingOverviewView,
    MatchingRuleDeleteView,
    MatchingRuleDetailView,
    MatchingRuleEditView,
    MatchingRuleListView,
    MatchingRuleVersionView,
)


urlpatterns = [
    path('', BookkeepingOverviewView.as_view(), name='bookkeeping_overview'),
    path(
        'transactions/<uuid:pk>/note/',
        BankTransactionNoteView.as_view(),
        name='bank_transaction_note',
    ),
    path(
        'transactions/<uuid:pk>/booking/',
        BookingEntryView.as_view(),
        name='bank_transaction_booking',
    ),
    path(
        'matching-rules/',
        MatchingRuleListView.as_view(),
        name='matching_rule_list',
    ),
    path(
        'matching-rules/<uuid:pk>/',
        MatchingRuleDetailView.as_view(),
        name='matching_rule_detail',
    ),
    path(
        'matching-rules/<uuid:pk>/edit/',
        MatchingRuleEditView.as_view(),
        name='matching_rule_edit',
    ),
    path(
        'matching-rules/<uuid:pk>/version/',
        MatchingRuleVersionView.as_view(),
        name='matching_rule_version',
    ),
    path(
        'matching-rules/<uuid:pk>/delete/',
        MatchingRuleDeleteView.as_view(),
        name='matching_rule_delete',
    ),
]
