import reviewboard.diffviewer.parser as diffparser

from reviewboard.scmtools.errors import FileNotFoundError


class ChangeSet:
    def __init__(self):
        self.changenum = None
        self.summary = ""
        self.description = ""
        self.testing_done = ""
        self.branch = ""
        self.bugs_closed = []
        self.files = []
        self.username = ""


class Revision(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == str(other)

    def __ne__(self, other):
        return self.name != str(other)

    def __repr__(self):
        return '<Revision: %s>' % self.name


HEAD = Revision("HEAD")
UNKNOWN = Revision('UNKNOWN')
PRE_CREATION = Revision("PRE-CREATION")


class SCMTool:
    name = None

    def __init__(self, repository):
        self.repository = repository
        self.uses_atomic_revisions = False
        self.diff_uses_changeset_ids = False

    def get_file(self, path, revision=None):
        raise NotImplementedError

    def file_exists(self, path, revision=HEAD):
        try:
            self.get_file(path, revision)
            return True
        except FileNotFoundError, e:
            return False

    def parse_diff_revision(self, file_str, revision_str):
        raise NotImplementedError

    def get_diffs_use_absolute_paths(self):
        return False

    def get_changeset(self, changesetid):
        raise NotImplementedError

    def get_pending_changesets(self, userid):
        raise NotImplementedError

    def get_filenames_in_revision(self, revision):
        raise NotImplementedError

    def get_repository_info(self):
        raise NotImplementedError

    def get_fields(self):
        # This is kind of a crappy mess in terms of OO design.  Oh well.
        # Return a list of fields which are valid for this tool in the "new
        # review request" page.
        raise NotImplementedError

    def get_parser(self, data):
        return diffparser.DiffParser(data)
