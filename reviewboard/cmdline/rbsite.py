#!/usr/bin/env python

import getpass
import imp
import os
import pkg_resources
import platform
import re
import shutil
import sys
import textwrap
import warnings
from optparse import OptionGroup, OptionParser
from random import choice


DOCS_BASE = "http://www.reviewboard.org/docs/manual/dev/"


# See if GTK is a possibility.
try:
    # Disable the gtk warning we might hit. This is because pygtk will
    # yell if it can't access X.
    warnings.simplefilter("ignore")

    import pygtk
    pygtk.require('2.0')
    import gtk
    can_use_gtk = True

    gtk.init_check()
except:
    can_use_gtk = False

# Reset the warnings so we don't ignore everything.
warnings.resetwarnings()


VERSION = "0.1"
DEBUG = False


# Global State
options = None
args = None
site = None
ui = None


class Dependencies(object):
    memcached_modules = ["cmemcache", "memcache"]
    sqlite_modules = ["pysqlite2", "sqlite3"]
    mysql_modules = ["MySQLdb"]
    postgresql_modules = ["psycopg2"]

    cache_dependency_info = {
        'required': False,
        'title': 'Server Cache',
        'dependencies': [
            ("memcached", memcached_modules),
        ],
    }

    db_dependency_info = {
        'required': True,
        'title': 'Databases',
        'dependencies': [
            ("sqlite3", sqlite_modules),
            ("MySQL", mysql_modules),
            ("PostgreSQL", postgresql_modules)
        ],
    }

    @classmethod
    def get_support_memcached(cls):
        return cls.has_modules(cls.memcached_modules)

    @classmethod
    def get_support_mysql(cls):
        return cls.has_modules(cls.mysql_modules)

    @classmethod
    def get_support_postgresql(cls):
        return cls.has_modules(cls.postgresql_modules)

    @classmethod
    def get_support_sqlite(cls):
        return cls.has_modules(cls.sqlite_modules)

    @classmethod
    def get_missing(cls):
        fatal = False
        missing_groups = []

        for dep_info in [cls.cache_dependency_info,
                         cls.db_dependency_info]:
            missing_deps = []

            for desc, modules in dep_info['dependencies']:
                if not cls.has_modules(modules):
                    missing_deps.append("%s (%s)" % (desc, ", ".join(modules)))

            if missing_deps:
                if (dep_info['required'] and
                    len(missing_deps) == len(dep_info['dependencies'])):
                    fatal = True
                    text = "%s (required)" % dep_info['title']
                else:
                    text = "%s (optional)" % dep_info['title']

                missing_groups.append({
                    'title': text,
                    'dependencies': missing_deps,
                })

        return fatal, missing_groups

    @classmethod
    def has_modules(cls, names):
        """
        Returns whether or not one of the specified modules is installed.
        """
        for name in names:
            try:
                __import__(name)
                return True
            except ImportError:
                continue

        return False


class Site(object):
    def __init__(self, install_dir):
        self.install_dir = install_dir
        self.abs_install_dir = os.path.abspath(install_dir)
        self.site_id = \
            os.path.basename(install_dir).replace(" ", "_").replace(".", "_")

        # State saved during installation
        self.domain_name = None
        self.site_root = None
        self.media_url = None
        self.db_type = None
        self.db_name = None
        self.db_host = None
        self.db_port = None
        self.db_user = None
        self.db_pass = None
        self.cache_type = None
        self.cache_info = None
        self.web_server_type = None
        self.python_loader = None
        self.admin_user = None
        self.admin_password = None

    def rebuild_site_directory(self):
        """
        Rebuilds the site hierarchy.
        """
        htdocs_dir = os.path.join(self.install_dir, "htdocs")
        media_dir = os.path.join(htdocs_dir, "media")

        self.mkdir(self.install_dir)
        self.mkdir(os.path.join(self.install_dir, "logs"))
        self.mkdir(os.path.join(self.install_dir, "conf"))

        self.mkdir(os.path.join(self.install_dir, "tmp"))
        os.chmod(os.path.join(self.install_dir, "tmp"), 0777)

        if self.db_type == "sqlite3":
            self.mkdir(os.path.join(self.install_dir, "db"))

        self.mkdir(htdocs_dir)
        self.mkdir(media_dir)

        # TODO: In the future, support changing ownership of these
        #       directories.
        self.mkdir(os.path.join(media_dir, "uploaded"))
        self.mkdir(os.path.join(media_dir, "uploaded", "images"))

        self.link_pkg_dir("reviewboard",
                          "htdocs/errordocs",
                          os.path.join("htdocs", "errordocs"))

        media_base = os.path.join("htdocs", "media")
        rb_djblets_src = "htdocs/media/djblets"
        rb_djblets_dest = os.path.join(media_base, "djblets")

        for media_dir in ["admin", "rb"]:
            path = os.path.join(media_base, media_dir)
            self.link_pkg_dir("reviewboard",
                              "htdocs/media/%s" % media_dir,
                              os.path.join(media_base, media_dir))

        # Link from Djblets if available.
        if pkg_resources.resource_exists("djblets", "media"):
            self.link_pkg_dir("djblets", "media", rb_djblets_dest)
        elif pkg_resources.resource_exists("reviewboard", rb_djblets_src):
            self.link_pkg_dir("reviewboard", rb_djblets_src,
                              rb_djblets_dest)
        else:
            ui.error("Unable to find the Djblets media path. Make sure "
                     "Djblets is installed and try this again.")


        # Generate a .htaccess file that enables compression and
        # never expires various file types.
        path = os.path.join(self.install_dir, media_base, ".htaccess")
        fp = open(path, "w")
        fp.write('<IfModule mod_expires.c>\n')
        fp.write('  <FilesMatch "\.(jpg|gif|png|css|js|htc)">\n')
        fp.write('    ExpiresActive on\n')
        fp.write('    ExpiresDefault "access plus 1 year"\n')
        fp.write('  </FilesMatch>\n')
        fp.write('</IfModule>\n')
        fp.write('\n')
        fp.write('<IfModule mod_deflate.c>\n')

        for mimetype in ["text/html", "text/plain", "text/xml",
                         "text/css", "text/javascript",
                         "application/javascript",
                         "application/x-javascript"]:
            fp.write("  AddOutputFilterByType DEFLATE %s\n" % mimetype)

        fp.write('</IfModule>\n')
        fp.close()

    def setup_settings(self):
        # Make sure that we have our settings_local.py in our path for when
        # we need to run manager commands.
        sys.path.insert(0, os.path.join(self.abs_install_dir, "conf"))

    def generate_config_files(self):
        web_conf_filename = ""
        enable_fastcgi = False

        if self.web_server_type == "apache":
            if self.python_loader == "modpython":
                web_conf_filename = "apache-modpython.conf"
            elif self.python_loader == "fastcgi":
                web_conf_filename = "apache-fastcgi.conf"
                enable_fastcgi = True
            else:
                # Should never be reached.
                assert False
        elif self.web_server_type == "lighttpd":
            web_conf_filename = "lighttpd.conf"
            enable_fastcgi = True
        else:
            # Should never be reached.
            assert False

        conf_dir = os.path.join(self.install_dir, "conf")
        htdocs_dir = os.path.join(self.install_dir, "htdocs")

        self.process_template("cmdline/conf/%s.in" % web_conf_filename,
                              os.path.join(conf_dir, web_conf_filename))
        self.process_template("cmdline/conf/search-cron.conf.in",
                              os.path.join(conf_dir, "search-cron.conf"))
        if enable_fastcgi:
            fcgi_filename = os.path.join(htdocs_dir, "reviewboard.fcgi")
            self.process_template("cmdline/conf/reviewboard.fcgi.in",
                                  fcgi_filename)
            os.chmod(fcgi_filename, 0755)

        # Generate a secret key based on Django's code.
        secret_key = ''.join([
            choice('abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)')
            for i in range(50)
        ])

        # Generate the settings_local.py
        fp = open(os.path.join(conf_dir, "settings_local.py"), "w")
        fp.write("# Site-specific configuration settings for Review Board\n")
        fp.write("# Definitions of these settings can be found at\n")
        fp.write("# http://docs.djangoproject.com/en/dev/ref/settings/\n")
        fp.write("\n")
        fp.write("# Database configuration\n")

        db_engine = self.db_type
        if db_engine == "postgresql":
            db_engine = "postgresql_psycopg2"

        fp.write("DATABASE_ENGINE = '%s'\n" % db_engine)
        fp.write("DATABASE_NAME = '%s'\n" % self.db_name.replace("\\", "\\\\"))

        if self.db_type != "sqlite3":
            fp.write("DATABASE_USER = '%s'\n" % (self.db_user or ""))
            fp.write("DATABASE_PASSWORD = '%s'\n" % (self.db_pass or ""))
            fp.write("DATABASE_HOST = '%s'\n" % (self.db_host or ""))
            fp.write("DATABASE_PORT = '%s'\n" % (self.db_port or ""))

        fp.write("\n")
        fp.write("# Unique secret key. Don't share this with anybody.\n")
        fp.write("SECRET_KEY = '%s'\n" % secret_key)
        fp.write("\n")
        fp.write("# Cache backend settings.\n")
        fp.write("CACHE_BACKEND = '%s'\n" % self.cache_info)
        fp.write("\n")
        fp.write("# Extra site information.\n")
        fp.write("SITE_ID = 1\n")
        fp.write("SITE_ROOT = '%s'\n" % self.site_root)
        fp.write("FORCE_SCRIPT_NAME = ''\n")
        fp.write("DEBUG = False\n")
        fp.close()

        self.setup_settings()

    def sync_database(self):
        """
        Synchronizes the database.
        """
        self.run_manage_command("syncdb", ["--noinput"])
        self.run_manage_command("registerscmtools")

    def migrate_database(self):
        """
        Performs a database migration.
        """
        self.run_manage_command("evolve", ["--noinput", "--execute"])

    def create_admin_user(self):
        """
        Creates an administrator user account.
        """
        cwd = os.getcwd()
        os.chdir(self.abs_install_dir)

        from django.contrib.auth.models import User

        User.objects.create_superuser(self.admin_user, self.admin_email,
                                      self.admin_password)

        os.chdir(cwd)

    def run_manage_command(self, cmd, params=None):
        cwd = os.getcwd()
        os.chdir(self.abs_install_dir)

        try:
            from django.core.management import execute_manager
            from reviewboard.admin.migration import fix_django_evolution_issues
            import reviewboard.settings

            if not params:
                params = []

            if DEBUG:
                params.append("--verbosity=0")

            fix_django_evolution_issues(reviewboard.settings)
            execute_manager(reviewboard.settings, [__file__, cmd] + params)
        except ImportError, e:
            ui.error("Unable to execute the manager command %s: %s" %
                     (cmd, e))

        os.chdir(cwd)

    def mkdir(self, dirname):
        """
        Creates a directory, but only if it doesn't already exist.
        """
        if not os.path.exists(dirname):
            os.mkdir(dirname)

    def link_pkg_dir(self, pkgname, src_path, dest_path, replace=True):
        src_dir = pkg_resources.resource_filename(pkgname, src_path)
        dest_dir = os.path.join(self.install_dir, dest_path)

        if os.path.islink(dest_dir) and not os.path.exists(dest_dir):
            os.unlink(dest_dir)

        if os.path.exists(dest_dir):
            if not replace:
                return

            if os.path.islink(dest_dir):
                os.unlink(dest_dir)
            else:
                shutil.rmtree(dest_dir)

        if options.copy_media:
            shutil.copytree(src_dir, dest_dir)
        else:
            os.symlink(src_dir, dest_dir)

    def process_template(self, template_path, dest_filename):
        """
        Generates a file from a template.
        """
        domain_name_escaped = self.domain_name.replace(".", "\\.")
        template = pkg_resources.resource_string("reviewboard", template_path)
        sitedir = os.path.abspath(self.install_dir).replace("\\", "/")

        # Check if this is a .exe.
        if (hasattr(sys, "frozen") or    # new py2exe
            hasattr(sys, "importers") or # new py2exe
            imp.is_frozen("__main__")):  # tools/freeze
            rbsite_path = sys.executable
        else:
            rbsite_path = '"%s" "%s"' % (sys.executable, sys.argv[0])

        data = {
            'rbsite': rbsite_path,
            'sitedir': sitedir,
            'sitedomain': self.domain_name,
            'sitedomain_escaped': domain_name_escaped,
            'siteid': self.site_id,
            'siteroot': self.site_root,
        }

        template = re.sub("@([a-z_]+)@", lambda m: data.get(m.group(1)),
                          template)

        fp = open(dest_filename, "w")
        fp.write(template)
        fp.close()


class UIToolkit(object):
    """
    An abstract class that forms the basis for all UI interaction.
    Subclasses can override this to provide new ways of representing the UI
    to the user.
    """
    def run(self):
        """
        Runs the UI.
        """
        pass

    def page(self, text, allow_back=True, is_visible_func=None,
             on_show_func=None):
        """
        Adds a new "page" to display to the user. Input and text are
        associated with this page and may be displayed immediately or
        later, depending on the toolkit.

        If is_visible_func is specified and returns False, this page will
        be skipped.
        """
        return None

    def prompt_input(self, page, prompt, default=None, password=False,
                     normalize_func=None, save_obj=None, save_var=None):
        """
        Prompts the user for some text. This may contain a default value.
        """
        raise NotImplemented

    def prompt_choice(self, page, prompt, choices,
                      save_obj=None, save_var=None):
        """
        Prompts the user for an item amongst a list of choices.
        """
        raise NotImplemented

    def text(self, page, text):
        """
        Displays a block of text to the user.
        """
        raise NotImplemented

    def urllink(self, page, url):
        """
        Displays a URL to the user.
        """
        raise NotImplemented

    def itemized_list(self, page, title, items):
        """
        Displays an itemized list.
        """
        raise NotImplemented

    def step(self, page, text, func):
        """
        Adds a step of a multi-step operation. This will indicate when
        it's starting and when it's complete.
        """
        raise NotImplemented

    def error(self, text, done_func=None):
        """
        Displays a block of error text to the user.
        """
        raise NotImplemented


class ConsoleUI(UIToolkit):
    """
    A UI toolkit that simply prints to the console.
    """
    def __init__(self):
        super(UIToolkit, self).__init__()

        self.header_wrapper = textwrap.TextWrapper(initial_indent="* ",
                                                   subsequent_indent="  ")

        indent_str = " " * 4
        self.text_wrapper = textwrap.TextWrapper(initial_indent=indent_str,
                                                 subsequent_indent=indent_str,
                                                 break_long_words=False)

        self.error_wrapper = textwrap.TextWrapper(initial_indent="[!] ",
                                                  subsequent_indent="    ",
                                                  break_long_words=False)

    def page(self, text, allow_back=True, is_visible_func=None,
             on_show_func=None):
        """
        Adds a new "page" to display to the user.

        In the console UI, we only care if we need to display or ask questions
        for this page. Our representation of a page in this case is simply
        a boolean value. If False, nothing associated with this page will
        be displayed to the user.
        """
        visible = not is_visible_func or is_visible_func()

        if not visible:
            return False

        if on_show_func:
            on_show_func()

        print
        print
        print self.header_wrapper.fill(text)

        return True

    def prompt_input(self, page, prompt, default=None, password=False,
                     normalize_func=None, save_obj=None, save_var=None):
        """
        Prompts the user for some text. This may contain a default value.
        """
        assert save_obj
        assert save_var

        if not page:
            return

        if default:
            self.text(page, "The default is %s" % default)
            prompt = "%s [%s]" % (prompt, default)

        print

        prompt += ": "
        value = None

        while not value:
            if password:
                value = getpass.getpass(prompt)
            else:
                value = raw_input(prompt)

            if not value:
                if default:
                    value = default
                else:
                    self.error("You must answer this question.")

        if normalize_func:
            value = normalize_func(value)

        setattr(save_obj, save_var, value)

    def prompt_choice(self, page, prompt, choices,
                      save_obj=None, save_var=None):
        """
        Prompts the user for an item amongst a list of choices.
        """
        assert save_obj
        assert save_var

        if not page:
            return

        self.text(page, "You can type either the name or the number "
                        "from the list below.")

        valid_choices = []
        i = 0

        for choice in choices:
            if isinstance(choice, basestring):
                text = choice
                enabled = True
            else:
                text, enabled = choice

            if enabled:
                self.text(page, "(%d) %s\n" % (i + 1, text),
                          leading_newline=(i == 0))
                valid_choices.append(text)
                i += 1

        print

        prompt += ": "
        choice = None

        while not choice:
            choice = raw_input(prompt)

            if choice not in valid_choices:
                try:
                    i = int(choice) - 1
                    if 0 <= i < len(valid_choices):
                        choice = valid_choices[i]
                        break
                except ValueError:
                    pass

                self.error("'%s' is not a valid option." % choice)
                choice = None

        setattr(save_obj, save_var, choice)

    def text(self, page, text, leading_newline=True):
        """
        Displays a block of text to the user.

        This will wrap the block to fit on the user's screen.
        """
        if not page:
            return

        if leading_newline:
            print

        print self.text_wrapper.fill(text)

    def urllink(self, page, url):
        """
        Displays a URL to the user.
        """
        self.text(page, url)

    def itemized_list(self, page, title, items):
        """
        Displays an itemized list.
        """
        if title:
            self.text(page, "%s:" % title)

        for item in items:
            self.text(page, "    * %s" % item, False)

    def step(self, page, text, func):
        """
        Adds a step of a multi-step operation. This will indicate when
        it's starting and when it's complete.
        """
        sys.stdout.write("%s ... " % text)
        func()
        print "OK"

    def error(self, text, done_func=None):
        """
        Displays a block of error text to the user.
        """
        print
        print self.error_wrapper.fill(text)

        if done_func:
            done_func()


class GtkUI(UIToolkit):
    """
    A UI toolkit that uses GTK to display a wizard.
    """
    def __init__(self):
        self.pages = []
        self.page_stack = []

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("Review Board Site Tool")
        self.window.set_default_size(300, 500)
        self.window.set_border_width(12)
        self.window.set_resizable(False)
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_position(gtk.WIN_POS_CENTER_ALWAYS)

        vbox = gtk.VBox(False, 12)
        vbox.show()
        self.window.add(vbox)

        self.notebook = gtk.Notebook()
        self.notebook.show()
        vbox.pack_start(self.notebook, True, True, 0)
        self.notebook.set_show_border(False)
        self.notebook.set_show_tabs(False)

        self.bbox = gtk.HButtonBox()
        self.bbox.show()
        vbox.pack_start(self.bbox, False, False, 0)
        self.bbox.set_layout(gtk.BUTTONBOX_END)
        self.bbox.set_spacing(6)

        button = gtk.Button(stock=gtk.STOCK_CANCEL)
        button.show()
        self.bbox.pack_start(button, False, False, 0)
        button.connect('clicked', lambda w: self.quit())

        self.prev_button = gtk.Button(stock=gtk.STOCK_GO_BACK)
        self.prev_button.show()
        self.bbox.pack_start(self.prev_button, False, False, 0)
        self.prev_button.connect('clicked', self.previous_page)

        self.next_button = gtk.Button(stock=gtk.STOCK_GO_FORWARD)
        self.next_button.show()
        self.bbox.pack_start(self.next_button, False, False, 0)
        self.next_button.connect('clicked', self.next_page)
        self.next_button.set_flags(gtk.CAN_DEFAULT)
        self.next_button.grab_default()
        self.next_button.grab_focus()

        self.close_button = gtk.Button(stock=gtk.STOCK_CLOSE)
        self.bbox.pack_start(self.close_button, False, False, 0)
        self.close_button.connect('clicked', lambda w: self.quit())

    def run(self):
        if self.pages:
            self.window.show()
            self.page_stack.append(self.pages[0])
            self.update_buttons()

        gtk.main()

    def quit(self):
        gtk.main_quit()

    def update_buttons(self):
        cur_page = self.page_stack[-1]
        cur_page_num = self.notebook.get_current_page()

        self.prev_button.set_sensitive(cur_page_num > 0 and
                                       cur_page['allow_back'])

        if cur_page_num == len(self.pages) - 1:
            self.close_button.show()
            self.next_button.hide()
        else:
            allow_next = True

            for validator in cur_page['validators']:
                if not validator():
                    allow_next = False
                    break

            self.close_button.hide()
            self.next_button.show()
            self.next_button.set_sensitive(allow_next)

    def previous_page(self, widget):
        self.page_stack.pop()
        self.notebook.set_current_page(self.page_stack[-1]['index'])
        self.update_buttons()

    def next_page(self, widget):
        new_page_index = self.notebook.get_current_page() + 1

        for i in range(new_page_index, len(self.pages)):
            page = self.pages[i]

            if not page['is_visible_func'] or page['is_visible_func']():
                page_info = self.pages[i]

                self.notebook.set_current_page(i)
                self.page_stack.append(page)
                self.update_buttons()

                for func in page_info['on_show_funcs']:
                    func()

                return

    def page(self, text, allow_back=True, is_visible_func=None,
             on_show_func=None):
        vbox = gtk.VBox(False, 12)
        vbox.show()
        self.notebook.append_page(vbox)

        label = gtk.Label("<big><b>%s</b></big>" % text)
        label.show()
        vbox.pack_start(label, False, True, 0)
        label.set_alignment(0, 0)
        label.set_use_markup(True)

        page = {
            'is_visible_func': is_visible_func,
            'widget': vbox,
            'index': len(self.pages),
            'allow_back': allow_back,
            'label_sizegroup': gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL),
            'validators': [],
            'on_show_funcs': [],
        }

        if on_show_func:
            page['on_show_funcs'].append(on_show_func)

        self.pages.append(page)

        return page

    def prompt_input(self, page, prompt, default=None, password=False,
                     normalize_func=None, save_obj=None, save_var=None):
        def save_input(widget=None, event=None):
            value = entry.get_text()

            if normalize_func:
                value = normalize_func(value)

            setattr(save_obj, save_var, value)

            self.update_buttons()

        hbox = gtk.HBox(False, 6)
        hbox.show()
        page['widget'].pack_start(hbox, False, False, 0)

        label = gtk.Label("<b>%s:</b>" % prompt)
        label.show()
        hbox.pack_start(label, False, True, 0)
        label.set_alignment(0, 0.5)
        label.set_line_wrap(True)
        label.set_use_markup(True)

        page['label_sizegroup'].add_widget(label)

        entry = gtk.Entry()
        entry.show()
        hbox.pack_start(entry, True, True, 0)
        entry.set_activates_default(True)

        if password:
            entry.set_visibility(False)

        if default:
            entry.set_text(default)

        entry.connect("key_release_event", save_input)

        page.setdefault('entries', []).append(entry)
        page['validators'].append(lambda: entry.get_text() != "")
        page['on_show_funcs'].append(save_input)

        # If this is the first on the page, make sure it gets focus when
        # we switch to this page.
        if len(page['entries']) == 1:
            page['on_show_funcs'].append(entry.grab_focus)

    def prompt_choice(self, page, prompt, choices,
                      save_obj=None, save_var=None):
        """
        Prompts the user for an item amongst a list of choices.
        """
        def on_toggled(radio_button):
            if radio_button.get_active():
                setattr(save_obj, save_var, radio_button.get_label())

        hbox = gtk.HBox(False, 0)
        hbox.show()
        page['widget'].pack_start(hbox, False, True, 0)

        label = gtk.Label("    ")
        label.show()
        hbox.pack_start(label, False, False, 0)

        vbox = gtk.VBox(False, 6)
        vbox.show()
        hbox.pack_start(vbox, True, True, 0)

        label = gtk.Label("<b>%s:</b>" % prompt)
        label.show()
        vbox.pack_start(label, False, True, 0)
        label.set_alignment(0, 0)
        label.set_line_wrap(True)
        label.set_use_markup(True)

        buttons = []

        for choice in choices:
            if isinstance(choice, basestring):
                text = choice
                enabled = True
            else:
                text, enabled = choice

            radio_button = gtk.RadioButton(label=text, use_underline=False)
            radio_button.show()
            vbox.pack_start(radio_button, False, True, 0)
            buttons.append(radio_button)
            radio_button.set_sensitive(enabled)
            radio_button.connect('toggled', on_toggled)

            if buttons[0] != radio_button:
                radio_button.set_group(buttons[0])

        # Force this to save.
        on_toggled(buttons[0])

    def text(self, page, text):
        """
        Displays a block of text to the user.
        """
        label = gtk.Label(textwrap.fill(text, 80))
        label.show()
        page['widget'].pack_start(label, False, True, 0)
        label.set_alignment(0, 0)

    def urllink(self, page, url):
        """
        Displays a URL to the user.
        """
        link_button = gtk.LinkButton(url)
        link_button.show()
        page['widget'].pack_start(link_button, False, False, 0)
        link_button.set_alignment(0, 0)

    def itemized_list(self, page, title, items):
        """
        Displays an itemized list.
        """
        if title:
            label = gtk.Label()
            label.set_markup("<b>%s:</b>" % title)
            label.show()
            page['widget'].pack_start(label, False, True, 0)
            label.set_alignment(0, 0)

        for item in items:
            self.text(page, u"    \u2022 %s" % item)

    def step(self, page, text, func):
        """
        Adds a step of a multi-step operation. This will indicate when
        it's starting and when it's complete.
        """
        def call_func():
            self.bbox.set_sensitive(False)
            label.set_markup("<b>%s</b>" % text)

            while gtk.events_pending():
                gtk.main_iteration()

            func()

            label.set_text(text)
            self.bbox.set_sensitive(True)
            icon.set_from_stock(gtk.STOCK_APPLY, gtk.ICON_SIZE_MENU)

        hbox = gtk.HBox(False, 12)
        hbox.show()
        page['widget'].pack_start(hbox, False, False, 0)

        icon = gtk.Image()
        icon.show()
        hbox.pack_start(icon, False, False, 0)

        icon.set_size_request(*gtk.icon_size_lookup(gtk.ICON_SIZE_MENU))

        label = gtk.Label(text)
        label.show()
        hbox.pack_start(label, False, False, 0)
        label.set_alignment(0, 0)

        page['on_show_funcs'].append(call_func)

    def error(self, text, done_func=None):
        """
        Displays a block of error text to the user.
        """
        dlg = gtk.MessageDialog(self.window,
                                gtk.DIALOG_MODAL |
                                gtk.DIALOG_DESTROY_WITH_PARENT,
                                gtk.MESSAGE_ERROR,
                                gtk.BUTTONS_OK,
                                text)
        dlg.show()

        if not done_func:
            done_func = self.quit

        dlg.connect('response', lambda w, e: done_func())


class Command(object):
    needs_ui = False

    def add_options(self, parser):
        pass

    def run(self):
        pass


class InstallCommand(Command):
    """
    Installs a new Review Board site tree and generates web server
    configuration files. This will ask several questions about the
    site before performing the installation.
    """
    needs_ui = True

    def add_options(self, parser):
        isWin = (platform.system() == "Windows")

        group = OptionGroup(parser, "'install' command",
                            self.__doc__.strip())
        group.add_option("--copy-media", action="store_true",
                         dest="copy_media", default=isWin,
                         help="copy media files instead of symlinking")

        group.add_option("--noinput", action="store_true", default=False,
                         help="run non-interactively using configuration "
                              "provided in command-line options")
        group.add_option("--domain-name",
                         help="full domain name of the site, excluding the "
                              "http://, port or path")
        group.add_option("--site-root", default="/",
                         help="path to the site relative to the domain name")
        group.add_option("--media-url", default="media/",
                         help="the URL containing the media files")
        group.add_option("--db-type",
                         help="database type (mysql, postgresql or sqlite3)")
        group.add_option("--db-name", default="reviewboard",
                         help="database name (not for sqlite3)")
        group.add_option("--db-host", default="localhost",
                         help="database host (not for sqlite3)")
        group.add_option("--db-user",
                         help="database user (not for sqlite3)")
        group.add_option("--db-pass",
                         help="password for the database user "
                              "(not for sqlite3)")
        group.add_option("--cache-type",
                         help="cache server type (memcached or file)")
        group.add_option("--cache-info",
                         help="cache identifier (memcached connection string "
                              "or file cache directory)")
        group.add_option("--web-server-type",
                         help="web server (apache or lighttpd)")
        group.add_option("--python-loader",
                         help="python loader for apache (modpython or fastcgi)")
        group.add_option("--admin-user", default="admin",
                         help="the site administrator's username")
        group.add_option("--admin-password",
                         help="the site administrator's password")
        group.add_option("--admin-email",
                         help="the site administrator's e-mail address")

        parser.add_option_group(group)

    def run(self):
        if not self.check_permissions():
            return

        site.__dict__.update(options.__dict__)

        self.print_introduction()

        if self.print_missing_dependencies():
            # There were required dependencies missing. Don't show any more
            # pages.
            return

        if not options.noinput:
            self.ask_domain()
            self.ask_site_root()
            self.ask_media_url()
            self.ask_database_type()
            self.ask_database_name()
            self.ask_database_host()
            self.ask_database_login()
            self.ask_cache_type()
            self.ask_cache_info()
            self.ask_web_server_type()
            self.ask_python_loader()
            self.ask_admin_user()

        self.show_install_status()
        self.show_finished()

    def normalize_root_url_path(self, path):
        if not path.endswith("/"):
            path += "/"

        if not path.startswith("/"):
            path = "/" + path

        return path

    def normalize_media_url_path(self, path):
        if not path.endswith("/"):
            path += "/"

        if path.startswith("/"):
            path = path[1:]

        return path

    def check_permissions(self):
        # Make sure we can create the directory first.
        try:
            # TODO: Do some chown tests too.
            os.mkdir(site.install_dir)

            # Don't leave a mess. We'll actually do this at the end.
            os.rmdir(site.install_dir)
            return True
        except OSError:
            # Likely a permission error.
            ui.error("Unable to create the %s directory. Make sure "
                     "you're running as an administrator." % site.install_dir,
                     done_func=lambda: sys.exit(1))
            return False

    def print_introduction(self):
        page = ui.page("Welcome to the Review Board site installation wizard.")

        ui.text(page, "This will prepare a Review Board site installation in:")
        ui.text(page, site.abs_install_dir)
        ui.text(page, "We need to know a few things before we can prepare "
                      "your site for installation. This will only take a few "
                      "minutes.")

    def print_missing_dependencies(self):
        fatal, missing_dep_groups = Dependencies.get_missing()

        if missing_dep_groups:
            if fatal:
                page = ui.page("Required modules are missing.")
                ui.text(page, "You are missing Python modules that are "
                              "needed before the installation process. "
                              "You will need to install the necessary "
                              "modules and restart the install.")
            else:
                page = ui.page("Make sure you have the modules you need.")
                ui.text(page, "Depending on your installation, you may need "
                              "certain Python modules and servers that are "
                              "missing.")
                ui.text(page, "If you need support for any of the following, "
                              "you will need to install the necessary "
                              "modules and restart the install.")

            for group in missing_dep_groups:
                ui.itemized_list(page, group['title'], group['dependencies'])

        return fatal


    def ask_domain(self):
        page = ui.page("What's the domain name for this site?")

        ui.text(page, "This should be the full domain without the http://, "
                      "port or path.")

        ui.prompt_input(page, "Domain Name", site.domain_name,
                        save_obj=site, save_var="domain_name")

    def ask_site_root(self):
        page = ui.page("What URL path points to Review Board?")

        ui.text(page, "Typically, Review Board exists at the root of a URL. "
                      "For example, http://reviews.example.com/. In this "
                      "case, you would specify \"/\".")
        ui.text(page, "However, if you want to listen to, say, "
                      "http://example.com/reviews/, you can specify "
                      '"/reviews/".')
        ui.text(page, "Note that this is the path relative to the domain and "
                      "should not include the domain name.")

        ui.prompt_input(page, "Root Path", site.site_root,
                        normalize_func=self.normalize_root_url_path,
                        save_obj=site, save_var="site_root")

    def ask_media_url(self):
        page = ui.page("What URL will point to the media files?")

        ui.text(page, "While most installations distribute media files on "
                      "the same server as the rest of Review Board, some "
                      "custom installs may instead have a separate server "
                      "for this purpose.")

        ui.prompt_input(page, "Media URL", site.media_url,
                        normalize_func=self.normalize_media_url_path,
                        save_obj=site, save_var="media_url")

    def ask_database_type(self):
        page = ui.page("What database type will you be using?")

        ui.prompt_choice(page, "Database Type",
                         [("mysql", Dependencies.get_support_mysql()),
                          ("postgresql", Dependencies.get_support_postgresql()),
                          ("sqlite3", Dependencies.get_support_sqlite())],
                         save_obj=site, save_var="db_type")

    def ask_database_name(self):
        def determine_sqlite_path():
            site.db_name = sqlite_db_name

        sqlite_db_name = os.path.join(site.abs_install_dir, "db",
                                      "reviewboard.db")

        # Appears only if using sqlite.
        page = ui.page("Determining database file path.",
                       is_visible_func=lambda: site.db_type == "sqlite3",
                       on_show_func=determine_sqlite_path)

        ui.text(page, "The sqlite database file will be stored in %s" %
                      sqlite_db_name)
        ui.text(page, "If you are migrating from an existing "
                      "installation, you can move your existing "
                      "database there, or edit settings_local.py to "
                      "point to your old location.")

        # Appears only if not using sqlite.
        page = ui.page("What database name should Review Board use?",
                       is_visible_func=lambda: site.db_type != "sqlite3")

        ui.text(page, "You may need to create this database and grant a "
                      "user modification rights before continuing.")

        ui.prompt_input(page, "Database Name", site.db_name,
                        save_obj=site, save_var="db_name")

    def ask_database_host(self):
        def normalize_host_port(value):
            if ":" in value:
                value, site.db_port = value.split(":", 1)

            return value

        page = ui.page("What is the database server's address?",
                       is_visible_func=lambda: site.db_type != "sqlite3")

        ui.text(page, "This should be specified in hostname:port form. "
                      "The port is optional if you're using a standard "
                      "port for the database type.")

        ui.prompt_input(page, "Database Server", site.db_host,
                        normalize_func=normalize_host_port,
                        save_obj=site, save_var="db_host")

    def ask_database_login(self):
        page = ui.page("What is the login and password for this database?",
                       is_visible_func=lambda: site.db_type != "sqlite3")

        ui.text(page, "This must be a user that has creation and modification "
                      "rights on the database.")

        ui.prompt_input(page, "Database Username", site.db_user,
                        save_obj=site, save_var="db_user")
        ui.prompt_input(page, "Database Password", site.db_pass, password=True,
                        save_obj=site, save_var="db_pass")

    def ask_cache_type(self):
        page = ui.page("What cache mechanism should be used?")

        ui.text(page, "memcached is strongly recommended. Use it unless "
                      "you have a good reason not to.")

        ui.prompt_choice(page, "Cache Type",
                         [("memcached", Dependencies.get_support_memcached()),
                          "file"],
                         save_obj=site, save_var="cache_type")

    def ask_cache_info(self):
        # Appears only if using memcached.
        page = ui.page("What memcached connection string should be used?",
                       is_visible_func=lambda: site.cache_type == "memcached")

        ui.text(page, "This is generally in the format of "
                      "memcached://hostname:port/")

        ui.prompt_input(page, "Memcache Server",
                        site.cache_info or "memcached://localhost:11211/",
                        save_obj=site, save_var="cache_info")

        # Appears only if using file caching.
        page = ui.page("Where should the temporary cache files be stored?",
                       is_visible_func=lambda: site.cache_type == "file")

        ui.prompt_input(page, "Cache Directory",
                        site.cache_info or "/tmp/reviewboard_cache",
                        normalize_func=lambda value: "file://" + value,
                        save_obj=site, save_var="cache_info")

    def ask_web_server_type(self):
        page = ui.page("What web server will you be using?")

        ui.prompt_choice(page, "Web Server", ["apache", "lighttpd"],
                         save_obj=site, save_var="web_server_type")

    def ask_python_loader(self):
        page = ui.page("What Python loader module will you be using?",
                       is_visible_func=lambda: site.web_server_type == "apache")

        ui.text(page, "Based on our experiences, we recommend using "
                      "modpython with Review Board.")

        ui.prompt_choice(page, "Python Loader", ["modpython", "fastcgi"],
                         save_obj=site, save_var="python_loader")

    def ask_admin_user(self):
        page = ui.page("Create an administrator account")

        ui.text(page, "To configure Review Board, you'll need an "
                      "administrator account. It is advised to have one "
                      "administrator and then use that account to grant "
                      "administrator permissions to your personal user "
                      "account.")

        ui.text(page, "If you plan to use NIS or LDAP, use an account name "
                      "other than your NIS/LDAP account so as to prevent "
                      "conflicts.")

        ui.prompt_input(page, "Username", site.admin_user,
                        save_obj=site, save_var="admin_user")
        ui.prompt_input(page, "Password", site.admin_password, password=True,
                        save_obj=site, save_var="admin_password")
        ui.prompt_input(page, "E-Mail Address", site.admin_email,
                        save_obj=site, save_var="admin_email")

    def show_install_status(self):
        page = ui.page("Installing the site...", allow_back=False)
        ui.step(page, "Building site directories",
                site.rebuild_site_directory)
        ui.step(page, "Building site configuration files",
                site.generate_config_files)
        ui.step(page, "Creating database",
                site.sync_database)
        ui.step(page, "Performing migrations",
                site.migrate_database)
        ui.step(page, "Creating administrator account",
                site.create_admin_user)
        ui.step(page, "Saving site settings",
                self.save_settings)

    def show_finished(self):
        page = ui.page("The site has been installed", allow_back=False)
        ui.text(page, "The site has been installed in %s" % site.install_dir)
        ui.text(page, "Sample configuration files for web servers and "
                      "cron are available in the conf/ directory.")
        ui.text(page, "You need to modify the ownership of the "
                      "\"htdocs/media/uploaded\" directory and all of its "
                      "contents to be owned by the web server.")
        ui.text(page, "If using SQLite, you will also need to modify the "
                      "ownership of the \"db\" directory and its contents.")
        ui.text(page, "For more information, visit:")
        ui.urllink(page, "%sadmin/sites/creating-sites/" % DOCS_BASE)

    def save_settings(self):
        """
        Saves some settings in the database.
        """
        from django.contrib.sites.models import Site
        from djblets.siteconfig.models import SiteConfiguration

        cur_site = Site.objects.get_current()
        cur_site.domain = site.domain_name
        cur_site.save()

        if site.media_url.startswith("http"):
            site_media_url = site.media_url
        else:
            site_media_url = site.site_root + site.media_url

        site_media_root = os.path.join(site.abs_install_dir, "htdocs", "media")

        siteconfig = SiteConfiguration.objects.get_current()
        siteconfig.set("site_media_url", site_media_url)
        siteconfig.set("site_media_root", site_media_root)
        siteconfig.set("site_admin_name", site.admin_user)
        siteconfig.set("site_admin_email", site.admin_email)
        siteconfig.save()


class UpgradeCommand(Command):
    """
    Upgrades an existing site installation, synchronizing media trees and
    upgrading the database, unless otherwise specified.
    """
    def add_options(self, parser):
        group = OptionGroup(parser, "'upgrade' command",
                            self.__doc__.strip())
        group.add_option("--no-db-upgrade", action="store_false",
                         dest="upgrade_db", default=True,
                         help="don't upgrade the database")
        parser.add_option_group(group)

    def run(self):
        site.setup_settings()

        print "Rebuilding directory structure"
        site.rebuild_site_directory()

        if options.upgrade_db:
            print "Updating database. This may take a while."
            site.sync_database()
            site.migrate_database()


class ManageCommand(Command):
    """
    Runs a manage.py command on the site.
    """
    def run(self):
        site.setup_settings()

        if len(args) == 0:
            ui.error("A manage command is needed.",
                     done_func=lambda: sys.exit(1))
        else:
            site.run_manage_command(args[0], args[1:])
            sys.exit(0)


# A list of all commands supported by rb-site.
COMMANDS = {
    "install": InstallCommand(),
    "upgrade": UpgradeCommand(),
    "manage": ManageCommand(),
}


def parse_options(args):
    global options

    parser = OptionParser(usage="%prog command [options] path",
                          version="%prog " + VERSION)

    parser.add_option("--console",
                      action="store_true", dest="force_console", default=False,
                      help="force the console UI")
    parser.add_option("-d", "--debug",
                      action="store_true", dest="debug", default=DEBUG,
                      help="display debug output")


    sorted_commands = list(COMMANDS.keys())
    sorted_commands.sort()

    for cmd_name in sorted_commands:
        command = COMMANDS[cmd_name]
        command.add_options(parser)


    (options, args) = parser.parse_args(args)

    if options.noinput:
        options.force_console = True

    # We expect at least two args (command and install path)
    if len(args) < 2 or args[0] not in COMMANDS.keys():
        parser.print_help()
        sys.exit(1)

    command = args[0]
    install_dir = args[1]

    globals()["args"] = args[2:]

    return (command, install_dir)


def main():
    global site
    global ui

    command_name, install_dir = parse_options(sys.argv[1:])
    command = COMMANDS[command_name]
    site = Site(install_dir)

    if command.needs_ui and can_use_gtk and not options.force_console:
        ui = GtkUI()

    if not ui:
        ui = ConsoleUI()

    command.run()
    ui.run()


if __name__ == "__main__":
    main()
