import logging

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core import mail
from django.template import Context, Template
from django.test import TestCase

from djblets.siteconfig.models import SiteConfiguration

from reviewboard.reviews.email import get_email_address_for_user, \
                                      get_email_addresses_for_group, \
                                      mail_review_request, mail_review, \
                                      mail_reply
from reviewboard.reviews.models import Group, ReviewRequest, \
                                       ReviewRequestDraft, Review


class EmailTests(TestCase):
    """Tests the e-mail support."""
    fixtures = ['test_users', 'test_reviewrequests', 'test_scmtools']

    def setUp(self):
        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set("mail_send_review_mail", True)
        siteconfig.save()
        mail.outbox = []

    def testNewReviewRequestEmail(self):
        """Testing sending an e-mail when creating a new review request"""
        review_request = ReviewRequest.objects.get(
            summary="Made e-mail improvements")
        mail_review_request(review_request.submitter, review_request)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject,
                         "Review Request: Made e-mail improvements")
        self.assertValidRecipients(["grumpy", "doc"], [])

    def testReviewEmail(self):
        """Testing sending an e-mail when replying to a review request"""
        review_request = ReviewRequest.objects.get(
            summary="Add permission checking for JSON API")
        review = Review.objects.get(review_request=review_request,
                                    user__username="doc",
                                    base_reply_to__isnull=True)
        self.assertEqual(review.body_top, "Test")
        mail_review(review.user, review)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject,
                         "Re: Review Request: Add permission checking " +
                         "for JSON API")
        self.assertValidRecipients(["admin", "doc", "dopey", "grumpy"], [])

    def testReviewReplyEmail(self):
        """Testing sending an e-mail when replying to a review"""
        review_request = ReviewRequest.objects.get(
            summary="Add permission checking for JSON API")
        base_review = Review.objects.get(review_request=review_request,
                                         user__username="doc",
                                         base_reply_to__isnull=True)
        reply = Review.objects.get(base_reply_to=base_review,
                                   user__username="dopey")
        mail_reply(reply.user, reply)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject,
                         "Re: Review Request: Add permission checking " +
                         "for JSON API")
        self.assertValidRecipients(["admin", "doc", "dopey", "admin"], [])

    def testUpdateReviewRequestEmail(self):
        """Testing sending an e-mail when updating a review request"""
        review_request = ReviewRequest.objects.get(
            summary="Update for cleaned_data changes")
        review_request.email_message_id = "junk"
        mail_review_request(review_request.submitter, review_request)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject,
                         "Re: Review Request: Update for cleaned_data changes")
        self.assertValidRecipients(["dopey", "doc"], ["devgroup"])

    def assertValidRecipients(self, user_list, group_list):
        recipient_list = mail.outbox[0].to + mail.outbox[0].cc
        self.assertEqual(len(recipient_list), len(user_list) + len(group_list))

        for user in user_list:
            self.assert_(get_email_address_for_user(
                User.objects.get(username=user)) in recipient_list,
                u"user %s was not found in the recipient list" % user)

        for group in Group.objects.filter(name__in=group_list):
            for address in get_email_addresses_for_group(group):
                self.assert_(address in recipient_list,
                    u"group %s was not found in the recipient list" % address)


class DbQueryTests(TestCase):
    """Tests review request query utility functions."""
    fixtures = ['test_users', 'test_reviewrequests', 'test_scmtools']

    def testAllReviewRequests(self):
        """Testing get_all_review_requests"""
        self.assertValidSummaries(
            ReviewRequest.objects.public(
                User.objects.get(username="doc")), [
            "Comments Improvements",
            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements",
            "Error dialog",
            "Interdiff Revision Test",
        ])

        self.assertValidSummaries(
            ReviewRequest.objects.public(status=None), [
            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements",
            "Error dialog",
            "Improved login form",
            "Interdiff Revision Test",
        ])

        self.assertValidSummaries(
            ReviewRequest.objects.public(
                User.objects.get(username="doc"), status=None), [
            "Comments Improvements",
            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements",
            "Error dialog",
            "Improved login form",
            "Interdiff Revision Test",
        ])

    def testReviewRequestsToGroup(self):
        """Testing get_review_requests_to_group"""
        self.assertValidSummaries(
            ReviewRequest.objects.to_group("privgroup"),
            ["Add permission checking for JSON API"])

        self.assertValidSummaries(
            ReviewRequest.objects.to_group("privgroup", status=None),
            ["Add permission checking for JSON API"])

    def testReviewRequestsToUserGroups(self):
        """Testing get_review_requests_to_user_groups"""
        self.assertValidSummaries(
            ReviewRequest.objects.to_user_groups("doc"),
            ["Update for cleaned_data changes",
             "Add permission checking for JSON API"])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user_groups("doc", status=None),
            ["Update for cleaned_data changes",
             "Add permission checking for JSON API"])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user_groups("doc",
                User.objects.get(username="doc")),
            ["Comments Improvements",
             "Update for cleaned_data changes",
             "Add permission checking for JSON API"])

    def testReviewRequestsToUserDirectly(self):
        """Testing get_review_requests_to_user_directly"""
        self.assertValidSummaries(
            ReviewRequest.objects.to_user_directly("doc"),
            ["Add permission checking for JSON API",
             "Made e-mail improvements"])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user_directly("doc", status=None),
            ["Add permission checking for JSON API",
             "Made e-mail improvements",
             "Improved login form"])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user_directly("doc",
                User.objects.get(username="doc"), status=None),
            ["Add permission checking for JSON API",
             "Made e-mail improvements",
             "Improved login form"])

    def testReviewRequestsFromUser(self):
        """Testing get_review_requests_from_user"""
        self.assertValidSummaries(
            ReviewRequest.objects.from_user("doc"), [])

        self.assertValidSummaries(
            ReviewRequest.objects.from_user("doc", status=None),
            ["Improved login form"])

        self.assertValidSummaries(
            ReviewRequest.objects.from_user("doc",
                user=User.objects.get(username="doc"), status=None),
            ["Comments Improvements",
             "Improved login form"])

    def testReviewRequestsToUser(self):
        """Testing get_review_requests_to_user"""
        self.assertValidSummaries(
            ReviewRequest.objects.to_user("doc"), [
            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements"
        ])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user("doc", status=None), [

            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements",
            "Improved login form"
        ])

        self.assertValidSummaries(
            ReviewRequest.objects.to_user("doc",
                User.objects.get(username="doc"), status=None), [
            "Comments Improvements",
            "Update for cleaned_data changes",
            "Add permission checking for JSON API",
            "Made e-mail improvements",
            "Improved login form"
        ])

    def assertValidSummaries(self, review_requests, summaries):
        print review_requests
        r_summaries = [r.summary for r in review_requests]

        for summary in r_summaries:
            self.assert_(summary in summaries,
                         u'summary "%s" not found in summary list' % summary)

        for summary in summaries:
            self.assert_(summary in r_summaries,
                         u'summary "%s" not found in review request list' %
                         summary)


class ViewTests(TestCase):
    """Tests for views in reviewboard.reviews.views"""
    fixtures = ['test_users', 'test_reviewrequests', 'test_scmtools']

    def setUp(self):
        self.siteconfig = SiteConfiguration.objects.get_current()
        self.siteconfig.set("auth_require_sitewide_login", False)
        self.siteconfig.save()

    def getContextVar(self, response, varname):
        for context in response.context:
            if varname in context:
                return context[varname]

        return None

    def testReviewDetail0(self):
        """Testing review_detail redirect"""
        response = self.client.get('/r/1')
        self.assertEqual(response.status_code, 301)

    def testReviewDetail1(self):
        """Testing review_detail view (1)"""
        response = self.client.get('/r/1/')
        self.assertEqual(response.status_code, 200)

        request = self.getContextVar(response, 'review_request')
        self.assertEqual(request.submitter.username, 'doc')
        self.assertEqual(request.summary, 'Comments Improvements')
        self.assertEqual(request.description, '')
        self.assertEqual(request.testing_done, '')

        self.assertEqual(request.target_people.count(), 0)
        self.assertEqual(request.target_groups.count(), 1)
        self.assertEqual(request.target_groups.all()[0].name, 'devgroup')
        self.assertEqual(request.bugs_closed, '')
        self.assertEqual(request.status, 'P')

        # TODO - diff

    def testReviewDetail2(self):
        """Testing review_detail view (3)"""
        # Make sure this request is made while logged in, to catch the
        # login-only pieces of the review_detail view.
        self.client.login(username='admin', password='admin')

        response = self.client.get('/r/3/')
        self.assertEqual(response.status_code, 200)

        request = self.getContextVar(response, 'review_request')
        self.assertEqual(request.submitter.username, 'admin')
        self.assertEqual(request.summary, 'Add permission checking for JSON API')
        self.assertEqual(request.description,
                         'Added some user permissions checking for JSON API functions.')
        self.assertEqual(request.testing_done, 'Tested some functions.')

        self.assertEqual(request.target_people.count(), 2)
        self.assertEqual(request.target_people.all()[0].username, 'doc')
        self.assertEqual(request.target_people.all()[1].username, 'dopey')

        self.assertEqual(request.target_groups.count(), 1)
        self.assertEqual(request.target_groups.all()[0].name, 'privgroup')

        self.assertEqual(request.bugs_closed, '1234, 5678, 8765, 4321')
        self.assertEqual(request.status, 'P')

        # TODO - diff
        # TODO - reviews

        self.client.logout()

    def testReviewDetailSitewideLogin(self):
        """Testing review_detail view with site-wide login enabled"""
        self.siteconfig.set("auth_require_sitewide_login", True)
        self.siteconfig.save()
        response = self.client.get('/r/1/')
        self.assertEqual(response.status_code, 302)

    def testNewReviewRequest0(self):
        """Testing new_review_request view (basic responses)"""
        response = self.client.get('/r/new')
        self.assertEqual(response.status_code, 301)

        response = self.client.get('/r/new/')
        self.assertEqual(response.status_code, 302)

        self.client.login(username='grumpy', password='grumpy')

        response = self.client.get('/r/new/')
        self.assertEqual(response.status_code, 200)

        self.client.logout()

    # TODO - test the rest of that form

    def testReviewList(self):
        """Testing all_review_requests view"""
        self.client.login(username='grumpy', password='grumpy')

        response = self.client.get('/r/')
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 6)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Interdiff Revision Test')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Made e-mail improvements')
        self.assertEqual(datagrid.rows[2]['object'].summary,
                         'Improved login form')
        self.assertEqual(datagrid.rows[3]['object'].summary,
                         'Error dialog')
        self.assertEqual(datagrid.rows[4]['object'].summary,
                         'Update for cleaned_data changes')
        self.assertEqual(datagrid.rows[5]['object'].summary,
                         'Add permission checking for JSON API')

        self.client.logout()

    def testReviewListSitewideLogin(self):
        """Testing all_review_requests view with site-wide login enabled"""
        self.siteconfig.set("auth_require_sitewide_login", True)
        self.siteconfig.save()
        response = self.client.get('/r/')
        self.assertEqual(response.status_code, 302)

    def testSubmitterList(self):
        """Testing submitter_list view"""
        response = self.client.get('/users/')
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 4)
        self.assertEqual(datagrid.rows[0]['object'].username, 'admin')
        self.assertEqual(datagrid.rows[1]['object'].username, 'doc')
        self.assertEqual(datagrid.rows[2]['object'].username, 'dopey')
        self.assertEqual(datagrid.rows[3]['object'].username, 'grumpy')

    def testSubmitterListSitewideLogin(self):
        """Testing submitter_list view with site-wide login enabled"""
        self.siteconfig.set("auth_require_sitewide_login", True)
        self.siteconfig.save()
        response = self.client.get('/users/')
        self.assertEqual(response.status_code, 302)

    def testSubmitterListChars(self):
        """Testing the submitter list with various characters in the username"""
        # Test if this throws an exception. Bug #1250
        reverse('user', args=['user@example.com'])

    def testGroupList(self):
        """Testing group_list view"""
        response = self.client.get('/groups/')
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 4)
        self.assertEqual(datagrid.rows[0]['object'].name, 'devgroup')
        self.assertEqual(datagrid.rows[1]['object'].name, 'emptygroup')
        self.assertEqual(datagrid.rows[2]['object'].name, 'newgroup')
        self.assertEqual(datagrid.rows[3]['object'].name, 'privgroup')

    def testGroupListSitewideLogin(self):
        """Testing group_list view with site-wide login enabled"""
        self.siteconfig.set("auth_require_sitewide_login", True)
        self.siteconfig.save()
        response = self.client.get('/groups/')
        self.assertEqual(response.status_code, 302)

    def testDashboard1(self):
        """Testing dashboard view (incoming)"""
        self.client.login(username='doc', password='doc')

        response = self.client.get('/dashboard/', {'view': 'incoming'})
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 4)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Made e-mail improvements')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Update for cleaned_data changes')
        self.assertEqual(datagrid.rows[2]['object'].summary,
                         'Comments Improvements')
        self.assertEqual(datagrid.rows[3]['object'].summary,
                         'Add permission checking for JSON API')

        self.client.logout()

    def testDashboard2(self):
        """Testing dashboard view (outgoing)"""
        self.client.login(username='admin', password='admin')

        response = self.client.get('/dashboard/', {'view': 'outgoing'})
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 2)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Interdiff Revision Test')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Add permission checking for JSON API')

        self.client.logout()

    def testDashboard3(self):
        """Testing dashboard view (to-me)"""
        self.client.login(username='doc', password='doc')

        response = self.client.get('/dashboard/', {'view': 'to-me'})
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 2)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Made e-mail improvements')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Add permission checking for JSON API')

        self.client.logout()

    def testDashboard4(self):
        """Testing dashboard view (to-group devgroup)"""
        self.client.login(username='doc', password='doc')

        response = self.client.get('/dashboard/',
                                   {'view': 'to-group',
                                    'group': 'devgroup'})
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 2)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Update for cleaned_data changes')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Comments Improvements')

        self.client.logout()

    # Bug 892
    def testInterdiff(self):
        """Testing the diff viewer with interdiffs"""
        response = self.client.get('/r/8/diff/1-2/')

        # Useful for debugging any actual errors here.
        if response.status_code != 200:
            print "Error: %s" % self.getContextVar(response, 'error')
            print self.getContextVar(response, 'trace')

        self.assertEqual(response.status_code, 200)

        self.assertEqual(self.getContextVar(response, 'num_diffs'), 3)

        files = self.getContextVar(response, 'files')
        self.assert_(files)
        self.assertEqual(len(files), 2)

        self.assertEqual(files[0]['depot_filename'],
                         '/trunk/reviewboard/TESTING')
        self.assert_('fragment' in files[0])
        self.assert_('interfilediff' in files[0])

        self.assertEqual(files[1]['depot_filename'],
                         '/trunk/reviewboard/settings_local.py.tmpl')
        self.assert_('fragment' not in files[1])
        self.assert_('interfilediff' in files[1])

    # Bug 847
    def testInterdiffNewFile(self):
        """Testing the diff viewer with interdiffs containing new files"""
        response = self.client.get('/r/8/diff/2-3/')

        # Useful for debugging any actual errors here.
        if response.status_code != 200:
            print "Error: %s" % self.getContextVar(response, 'error')
            print self.getContextVar(response, 'trace')

        self.assertEqual(response.status_code, 200)

        self.assertEqual(self.getContextVar(response, 'num_diffs'), 3)

        files = self.getContextVar(response, 'files')
        self.assert_(files)
        self.assertEqual(len(files), 1)

        self.assertEqual(files[0]['depot_filename'],
                         '/trunk/reviewboard/NEW_FILE')
        self.assert_('fragment' in files[0])
        self.assert_('interfilediff' in files[0])

    def testDashboard5(self):
        """Testing dashboard view (mine)"""
        self.client.login(username='doc', password='doc')

        response = self.client.get('/dashboard/', {'view': 'mine'})
        self.assertEqual(response.status_code, 200)

        datagrid = self.getContextVar(response, 'datagrid')
        self.assert_(datagrid)
        self.assertEqual(len(datagrid.rows), 2)
        self.assertEqual(datagrid.rows[0]['object'].summary,
                         'Improved login form')
        self.assertEqual(datagrid.rows[1]['object'].summary,
                         'Comments Improvements')

        self.client.logout()


class DraftTests(TestCase):
    fixtures = ['test_users', 'test_reviewrequests', 'test_scmtools']

    def testDraftChanges(self):
        """Testing recording of draft changes."""
        draft = self.getDraft()
        review_request = draft.review_request

        old_summary = review_request.summary
        old_description = review_request.description
        old_testing_done = review_request.testing_done
        old_branch = review_request.branch
        old_bugs = review_request.get_bug_list()

        draft.summary = "New summary"
        draft.description = "New description"
        draft.testing_done = "New testing done"
        draft.branch = "New branch"
        draft.bugs_closed = "12, 34, 56"

        new_bugs = draft.get_bug_list()

        changes = draft.publish()
        fields = changes.fields_changed

        self.assert_("summary" in fields)
        self.assert_("description" in fields)
        self.assert_("testing_done" in fields)
        self.assert_("branch" in fields)
        self.assert_("bugs_closed" in fields)

        old_bugs_norm = set([(bug,) for bug in old_bugs])
        new_bugs_norm = set([(bug,) for bug in new_bugs])

        self.assertEqual(fields["summary"]["old"][0], old_summary)
        self.assertEqual(fields["summary"]["new"][0], draft.summary)
        self.assertEqual(fields["description"]["old"][0], old_description)
        self.assertEqual(fields["description"]["new"][0], draft.description)
        self.assertEqual(fields["testing_done"]["old"][0], old_testing_done)
        self.assertEqual(fields["testing_done"]["new"][0], draft.testing_done)
        self.assertEqual(fields["branch"]["old"][0], old_branch)
        self.assertEqual(fields["branch"]["new"][0], draft.branch)
        self.assertEqual(set(fields["bugs_closed"]["old"]), old_bugs_norm)
        self.assertEqual(set(fields["bugs_closed"]["new"]), new_bugs_norm)
        self.assertEqual(set(fields["bugs_closed"]["removed"]), old_bugs_norm)
        self.assertEqual(set(fields["bugs_closed"]["added"]), new_bugs_norm)

    def getDraft(self):
        """Convenience function for getting a new draft to work with."""
        return ReviewRequestDraft.create(ReviewRequest.objects.get(
            summary="Add permission checking for JSON API"))


class FieldTests(TestCase):
    # Bug #1352
    def testLongBugNumbers(self):
        """Testing review requests with very long bug numbers"""
        review_request = ReviewRequest()
        review_request.bugs_closed = \
            '12006153200030304432010,4432009'
        self.assertEqual(review_request.get_bug_list(),
                         ['4432009', '12006153200030304432010'])

    # Our _("(no summary)") string was failing in the admin UI, as
    # django.template.defaultfilters.stringfilter would fail on a
    # ugettext_lazy proxy object. We can use any stringfilter for this.
    #
    # Bug #1346
    def testNoSummary(self):
        """Testing review requests with no summary"""
        from django.template.defaultfilters import lower
        review_request = ReviewRequest()
        lower(unicode(review_request))


class ConcurrencyTests(TestCase):
    fixtures = ['test_users', 'test_reviewrequests', 'test_scmtools']

    def testDuplicateReviews(self):
        """Testing consolidation of duplicate reviews"""

        body_top = "This is the body_top."
        body_bottom = "This is the body_bottom."
        comment_text_1 = "Comment text 1"
        comment_text_2 = "Comment text 2"
        comment_text_3 = "Comment text 3"

        # Some objects we need.
        user = User.objects.get(username="doc")

        review_request = ReviewRequest.objects.get(
            summary="Add permission checking for JSON API")
        filediff = \
            review_request.diffset_history.diffsets.latest().files.all()[0]

        # Create the first review.
        review = Review(review_request=review_request, user=user)
        review.body_top = body_top
        review.save()
        master_review = review

        comment = review.comments.create(filediff=filediff, first_line=1)
        comment.text = comment_text_1
        comment.num_lines = 1
        comment.save()

        # Create the second review.
        review = Review(review_request=review_request, user=user)
        review.save()

        comment = review.comments.create(filediff=filediff, first_line=1)
        comment.text = comment_text_2
        comment.num_lines = 1
        comment.save()

        # Create the third review.
        review = Review(review_request=review_request, user=user)
        review.body_bottom = body_bottom
        review.save()

        comment = review.comments.create(filediff=filediff, first_line=1)
        comment.text = comment_text_3
        comment.num_lines = 1
        comment.save()

        # Now that we've made a mess, see if we get a single review back.
        logging.disable(logging.WARNING)
        review = review_request.get_pending_review(user)
        self.assert_(review)
        self.assertEqual(review.id, master_review.id)
        self.assertEqual(review.body_top, body_top)
        self.assertEqual(review.body_bottom, body_bottom)

        comments = list(review.comments.all())
        self.assertEqual(len(comments), 3)
        self.assertEqual(comments[0].text, comment_text_1)
        self.assertEqual(comments[1].text, comment_text_2)
        self.assertEqual(comments[2].text, comment_text_3)


class IfNeatNumberTagTests(TestCase):
    def testMilestones(self):
        """Testing the ifneatnumber tag with milestone numbers"""
        self.assertNeatNumberResult(100, "")
        self.assertNeatNumberResult(1000, "milestone")
        self.assertNeatNumberResult(10000, "milestone")
        self.assertNeatNumberResult(20000, "milestone")
        self.assertNeatNumberResult(20001, "")

    def testPalindrome(self):
        """Testing the ifneatnumber tag with palindrome numbers"""
        self.assertNeatNumberResult(101, "")
        self.assertNeatNumberResult(1001, "palindrome")
        self.assertNeatNumberResult(12321, "palindrome")
        self.assertNeatNumberResult(20902, "palindrome")
        self.assertNeatNumberResult(912219, "palindrome")
        self.assertNeatNumberResult(912218, "")

    def assertNeatNumberResult(self, rid, expected):
        t = Template(
            "{% load reviewtags %}"
            "{% ifneatnumber " + str(rid) + " %}"
            "{%  if milestone %}milestone{% else %}"
            "{%  if palindrome %}palindrome{% endif %}{% endif %}"
            "{% endifneatnumber %}")

        self.assertEqual(t.render(Context({})), expected)
