import pytz
import re
import urlparse

from django import forms
from django.contrib.sites.models import Site
from django.utils.translation import ugettext as _

from djblets.log import restart_logging
from djblets.siteconfig.forms import SiteSettingsForm

from reviewboard.admin.checks import get_can_enable_dns, \
                                     get_can_enable_ldap, \
                                     get_can_enable_search, \
                                     get_can_enable_syntax_highlighting

from reviewboard.admin.siteconfig import load_site_config


class GeneralSettingsForm(SiteSettingsForm):
    """
    General settings for Review Board.
    """
    server = forms.CharField(
        label=_("Server"),
        help_text=_("The URL of this Review Board server. This should not "
                    "contain the subdirectory Review Board is installed in."),
        widget=forms.TextInput(attrs={'size': '30'}))

    site_media_url = forms.CharField(
        label=_("Media URL"),
        help_text=_("The URL to the media files. Leave blank to use the "
                    "default media path on this server."),
        required=False,
        widget=forms.TextInput(attrs={'size': '30'}))

    site_admin_name = forms.CharField(
        label=_("Administrator Name"),
        required=True,
        widget=forms.TextInput(attrs={'size': '30'}))
    site_admin_email = forms.EmailField(
        label=_("Administrator E-Mail"),
        required=True,
        widget=forms.TextInput(attrs={'size': '30'}))

    locale_timezone = forms.ChoiceField(
        label=_("Time Zone"),
        required=True,
        choices=[(tz, tz) for tz in pytz.common_timezones],
        help_text=_("The time zone used for all dates on this server."))

    auth_anonymous_access = forms.BooleanField(
        label=_("Allow anonymous read-only access"),
        help_text=_("If checked, users will be able to view review requests "
                    "and diffs without logging in."),
        required=False)

    search_enable = forms.BooleanField(
        label=_("Enable search"),
        help_text=_("Provides a search field for quickly searching through "
                    "review requests."),
        required=False)

    search_index_file = forms.CharField(
        label=_("Search index file"),
        help_text=_("The file that search index data should be stored in."),
        required=False,
        widget=forms.TextInput(attrs={'size': '50'}))

    auth_backend = forms.ChoiceField(
        label=_("Authentication Method"),
        choices=(
            ("builtin", _("Standard registration")),
            ("ad",      _("Active Directory")),
            ("ldap",    _("LDAP")),
            ("nis",     _("NIS")),
            ("custom",  _("Custom"))
        ),
        help_text=_("The method Review Board should use for authenticating "
                    "users."),
        required=True)

    auth_enable_registration = forms.BooleanField(
        label=_("Enable registration"),
        help_text=_("Allow users to register new accounts."),
        required=False)

    auth_nis_email_domain = forms.CharField(
        label=_("E-Mail Domain"))

    # TODO: Invent a URIField and use it.
    auth_ldap_uri = forms.CharField(
        label=_("LDAP Server"),
        help_text=_("The LDAP server to authenticate with. "
                    "For example: ldap://localhost:389"))

    auth_ldap_base_dn = forms.CharField(
        label=_("LDAP Base DN"),
        help_text=_("The LDAP Base DN for performing LDAP searches.  For "
                    "example: ou=users,dc=example,dc=com"),
        required=True)

    auth_ldap_email_domain = forms.CharField(
        label=_("E-Mail Domain"),
        help_text=_("The domain name appended to the username to construct "
                    "the user's e-mail address. This takes precedence over "
                    '"E-Mail LDAP Attribute."'),
        required=False)

    auth_ldap_email_attribute = forms.CharField(
        label=_("E-Mail LDAP Attribute"),
        help_text=_("The attribute in the LDAP server that stores the user's "
                    "e-mail address. For example: mail"),
        required=False)

    auth_ldap_tls = forms.BooleanField(
        label=_("Use TLS for authentication"),
        required=False)

    auth_ldap_uid_mask = forms.CharField(
        label=_("User Mask"),
        initial="uid=%s,ou=users,dc=example,dc=com",
        help_text=_("The string representing the user. Use \"%(varname)s\" "
                    "where the username would normally go. For example: "
                    "(uid=%(varname)s)") %
                  {'varname': '%s'})

    auth_ldap_anon_bind_uid = forms.CharField(
        label=_("Anonymous User Mask"),
        help_text=_("The user mask string for anonymous users. If specified, "
                    "this should be in the same format as User Mask."),
        required=False)

    auth_ldap_anon_bind_passwd = forms.CharField(
        label=_("Anonymous User Password"),
        widget=forms.PasswordInput,
        help_text=_("The optional password for the anonymous user."),
        required=False)

    auth_ad_domain_name = forms.CharField(
        label=_("Domain name"),
        help_text=_("Enter the domain name to use, (ie. example.com). This will be "
                    "used to query for LDAP servers and to bind to the domain."),
        required=True)

    auth_ad_use_tls = forms.BooleanField(
        label=_("Use TLS for authentication"),
        required=False)

    auth_ad_find_dc_from_dns = forms.BooleanField(
        label=_("Find DC from DNS"),
        help_text=_("Query DNS to find which domain controller to use"),
        required=False)

    auth_ad_domain_controller = forms.CharField(
        label=_("Domain controller"),
        help_text=_("If not using DNS to find the DC specify the domain "
                    "controller here"),
        required=False)

    auth_ad_ou_name = forms.CharField(
        label=_("OU name"),
        help_text=_("Optionally restrict users to specified OU."),
        required=False)

    auth_ad_group_name = forms.CharField(
        label=_("Group name"),
        help_text=_("Optionally restrict users to specified group."),
        required=False)

    auth_ad_search_root = forms.CharField(
        label=_("Custom search root"),
        help_text=_("Optionally specify a custom search root, overriding "
                    "the built-in computed search root. If set, \"OU name\" "
                    "is ignored."),
        required=False)

    auth_ad_recursion_depth = forms.IntegerField(
        label=_("Recursion Depth"),
        help_text=_("Depth to recurse when checking group membership. 0 to turn off, -1 for unlimited."),
        required=False)

    custom_backends = forms.CharField(
        label=_("Backends"),
        help_text=_("A comma-separated list of custom auth backends. These "
                    "are represented as Python module paths."))


    def load(self):
        # First set some sane defaults.
        domain_method = self.siteconfig.get("site_domain_method")
        site = Site.objects.get_current()
        self.fields['server'].initial = "%s://%s" % (domain_method,
                                                     site.domain)
        self.fields['auth_anonymous_access'].initial = \
            not self.siteconfig.get("auth_require_sitewide_login")

        self.fields['custom_backends'].initial = \
            ', '.join(self.siteconfig.get('auth_custom_backends'))

        can_enable_search, reason = get_can_enable_search()
        if not can_enable_search:
            self.disabled_fields['search_enable'] = True
            self.disabled_fields['search_index_file'] = True
            self.disabled_reasons['search_enable'] = _(reason)

        can_enable_dns, reason = get_can_enable_dns()
        if not can_enable_dns:
            self.disabled_fields['auth_ad_find_dc_from_dns'] = _(reason)

        can_enable_ldap, reason = get_can_enable_ldap()

        if not can_enable_ldap:
            self.disabled_fields['auth_ldap_uri'] = True
            self.disabled_fields['auth_ldap_email_domain'] = True
            self.disabled_fields['auth_ldap_email_attribute'] = True
            self.disabled_fields['auth_ldap_tls'] = True
            self.disabled_fields['auth_ldap_base_dn'] = True
            self.disabled_fields['auth_ldap_uid_mask'] = True
            self.disabled_fields['auth_ldap_anon_bind_uid'] = True
            self.disabled_fields['auth_ldap_anon_bind_password'] = True

            self.disabled_fields['auth_ad_use_tls'] = True
            self.disabled_fields['auth_ad_group_name'] = True
            self.disabled_fields['auth_ad_recursion_depth'] = True
            self.disabled_fields['auth_ad_ou_name'] = True
            self.disabled_fields['auth_ad_search_root'] = True
            self.disabled_fields['auth_ad_find_dc_from_dns'] = True
            self.disabled_fields['auth_ad_domain_controller'] = True
            self.disabled_fields['auth_ad_domain_name'] = _(reason)

            self.disabled_reasons['auth_ldap_uri'] = _(reason)

        super(GeneralSettingsForm, self).load()


    def save(self):
        server = self.cleaned_data['server']

        if "://" not in server:
            # urlparse doesn't properly handle URLs without a scheme. It
            # believes the domain is actually the path. So we apply a prefix.
            server = "http://" + server

        url_parts = urlparse.urlparse(server)
        domain_method = url_parts[0]
        domain_name = url_parts[1]

        if domain_name.endswith("/"):
            domain_name = domain_name[:-1]

        site = Site.objects.get_current()
        site.domain = domain_name
        site.save()

        self.siteconfig.set("site_domain_method", domain_method)
        self.siteconfig.set("auth_require_sitewide_login",
                            not self.cleaned_data['auth_anonymous_access'])

        self.siteconfig.set('auth_custom_backends',
            re.split(r',\s*', self.cleaned_data['custom_backends']))

        super(GeneralSettingsForm, self).save()

        # Reload any important changes into the Django settings.
        load_site_config()

    def full_clean(self):
        def set_fieldset_required(fieldset_id, required):
            for fieldset in self.Meta.fieldsets:
                if 'id' in fieldset and fieldset['id'] == fieldset_id:
                    for field in fieldset['fields']:
                        self.fields[field].required = required

        if self.data:
            # Note that this isn't validated yet, but that's okay given our
            # usage. It's a bit of a hack though.
            auth_backend = self['auth_backend'].data or \
                           self.fields['auth_backend'].initial

            if auth_backend != "ldap":
                set_fieldset_required("auth_ldap", False)

            if auth_backend != "nis":
                set_fieldset_required("auth_nis", False)

            if auth_backend != "ad":
                set_fieldset_required("auth_ad", False)

            if auth_backend != "custom":
                set_fieldset_required("auth_custom", False)

        super(GeneralSettingsForm, self).full_clean()


    class Meta:
        title = _("General Settings")
        save_blacklist = ('server', 'auth_anonymous_access', 'custom_backends')

        fieldsets = (
            {
                'classes': ('wide',),
                'title':   _("Site Settings"),
                'fields':  ('server', 'site_media_url',
                            'site_admin_name',
                            'site_admin_email',
                            'locale_timezone',
                            'auth_anonymous_access'),
            },
            {
                'classes': ('wide',),
                'title':   _("Search"),
                'fields':  ('search_enable', 'search_index_file'),
            },
            {
                'classes': ('wide',),
                'title':   _("Advanced Authentication"),
                'fields':  ('auth_backend',),
            },
            {
                'id':      'auth_builtin',
                'classes': ('wide', 'hidden'),
                'title':   _("Basic Authentication Settings"),
                'fields':  ('auth_enable_registration',),
            },
            {
                'id':      'auth_nis',
                'classes': ('wide', 'hidden'),
                'title':   _("NIS Authentication Settings"),
                'fields':  ('auth_nis_email_domain',),
            },
            {
                'id':      'auth_ldap',
                'classes': ('wide', 'hidden'),
                'title':   _("LDAP Authentication Settings"),
                'fields':  ('auth_ldap_uri',
                            'auth_ldap_base_dn',
                            'auth_ldap_email_domain',
                            'auth_ldap_email_attribute',
                            'auth_ldap_tls',
                            'auth_ldap_uid_mask',
                            'auth_ldap_anon_bind_uid',
                            'auth_ldap_anon_bind_passwd'),
            },
            {
                'id':      'auth_ad',
                'classes': ('wide', 'hidden'),
                'title':   _("Active Directory Authentication Settings"),
                'fields':  ('auth_ad_domain_name',
                            'auth_ad_use_tls',
                            'auth_ad_find_dc_from_dns',
                            'auth_ad_domain_controller',
                            'auth_ad_ou_name',
                            'auth_ad_group_name',
                            'auth_ad_search_root',
                            'auth_ad_recursion_depth',
                            ),
            },
            {
                'id':      'auth_custom',
                'classes': ('wide', 'hidden'),
                'title':   _("Custom Authentication Settings"),
                'fields':  ('custom_backends',)
            },
        )


class EMailSettingsForm(SiteSettingsForm):
    """
    E-mail settings for Review Board.
    """
    mail_send_review_mail = forms.BooleanField(
        label=_("Send e-mails for review requests and reviews"),
        required=False)
    mail_host = forms.CharField(
        label=_("Mail Server"),
        required=False)
    mail_port = forms.IntegerField(
        label=_("Port"),
        required=False)
    mail_host_user = forms.CharField(
        label=_("Username"),
        required=False)
    mail_host_password = forms.CharField(
        widget=forms.PasswordInput,
        label=_("Password"),
        required=False)
    mail_use_tls = forms.BooleanField(
        label=_("Use TLS for authentication"),
        required=False)

    def save(self):
        super(EMailSettingsForm, self).save()

        # Reload any important changes into the Django settings.
        load_site_config()


    class Meta:
        title = _("E-Mail Settings")


class DiffSettingsForm(SiteSettingsForm):
    """
    Diff settings for Review Board.
    """
    diffviewer_syntax_highlighting = forms.BooleanField(
        label=_("Show syntax highlighting"),
        required=False)

    diffviewer_syntax_highlighting_threshold = forms.IntegerField(
        label=_("Syntax highlighting threshold"),
        help_text=_("Files with lines greater than this number will not have "
                    "syntax highlighting.  Enter 0 for no limit."),
        required=False)

    diffviewer_show_trailing_whitespace = forms.BooleanField(
        label=_("Show trailing whitespace"),
        help_text=_("Show excess trailing whitespace as red blocks. This "
                    "helps to visualize when a text editor added unwanted "
                    "whitespace to the end of a line."),
        required=False)

    include_space_patterns = forms.CharField(
        label=_("Show all whitespace for"),
        required=False,
        help_text=_("A comma-separated list of file patterns for which all "
                    "whitespace changes should be shown. "
                    "(e.g., \"*.py, *.txt\")"))

    diffviewer_context_num_lines = forms.IntegerField(
        label=_("Lines of Context"),
        help_text=_("The number of unchanged lines shown above and below "
                    "changed lines."),
        initial=5)

    diffviewer_paginate_by = forms.IntegerField(
        label=_("Paginate by"),
        help_text=_("The number of files to display per page in the diff "
                    "viewer."),
        initial=20)

    diffviewer_paginate_orphans = forms.IntegerField(
        label=_("Paginate orphans"),
        help_text=_("The number of extra files required before adding another "
                    "page to the diff viewer."),
        initial=10)

    def load(self):
        # TODO: Move this check into a dependencies module so we can catch it
        #       when the user starts up Review Board.
        can_syntax_highlight, reason = get_can_enable_syntax_highlighting()

        if not can_syntax_highlight:
            self.disabled_fields['diffviewer_syntax_highlighting'] = True
            self.disabled_reasons['diffviewer_syntax_highlighting'] = _(reason)
            self.disabled_fields['diffviewer_syntax_highlighting_threshold'] = True
            self.disabled_reasons['diffviewer_syntax_highlighting_threshold'] = _(reason)

        self.fields['include_space_patterns'].initial = \
            ', '.join(self.siteconfig.get('diffviewer_include_space_patterns'))

        super(DiffSettingsForm, self).load()

    def save(self):
        self.siteconfig.set('diffviewer_include_space_patterns',
            re.split(r",\s*", self.cleaned_data['include_space_patterns']))

        super(DiffSettingsForm, self).save()


    class Meta:
        title = _("Diff Viewer Settings")
        save_blacklist = ('include_space_patterns',)
        fieldsets = (
            {
                'title': _("General"),
                'classes': ('wide',),
                'fields': ('diffviewer_syntax_highlighting',
                           'diffviewer_syntax_highlighting_threshold',
                           'diffviewer_show_trailing_whitespace',
                           'include_space_patterns'),
            },
            {
                'title': _("Advanced"),
                'description': _(
                    "These are advanced settings that control the behavior "
                    "and display of the diff viewer. In general, these "
                    "settings do not need to be changed."
                ),
                'classes': ('wide',),
                'fields': ('diffviewer_context_num_lines',
                           'diffviewer_paginate_by',
                           'diffviewer_paginate_orphans')
            }
        )


class LoggingSettingsForm(SiteSettingsForm):
    """
    Logging settings for Review Board.
    """
    logging_enabled = forms.BooleanField(
        label=_("Enable logging"),
        help_text=_("Enables logging of Review Board operations. This is in "
                    "addition to your web server's logging and does not log "
                    "all page visits."),
        required=False)

    logging_directory = forms.CharField(
        label=_("Log directory"),
        help_text=_("The directory where log files will be stored. This must "
                    "be writable by the web server."),
        required=False)

    logging_allow_profiling = forms.BooleanField(
        label=_("Allow code profiling"),
        help_text=_("Logs the time spent on certain operations. This is "
                    "useful for debugging but may greatly increase the "
                    "size of log files."),
        required=False)

    def save(self):
        super(LoggingSettingsForm, self).save()

        # Reload any important changes into the Django settings.
        load_site_config()
        restart_logging()

    class Meta:
        title = _("Logging Settings")
        fieldsets = (
            {
                'title':   _('General'),
                'classes': ('wide',),
                'fields':  ('logging_enabled',
                            'logging_directory'),
            },
            {
                'title':   _('Advanced'),
                'classes': ('wide',),
                'fields':  ('logging_allow_profiling',),
            }
        )
