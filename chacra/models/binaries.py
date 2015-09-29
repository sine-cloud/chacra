import hashlib
import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.event import listen
from sqlalchemy.orm.exc import DetachedInstanceError
from chacra.models import Base
from chacra.models.repos import Repo
from chacra.controllers import util


class Binary(Base):

    __tablename__ = 'binaries'
    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False, index=True)
    path = Column(String(256))
    ref = Column(String(256), index=True)
    distro = Column(String(256), nullable=False, index=True)
    distro_version = Column(String(256), nullable=False, index=True)
    arch = Column(String(256), nullable=False, index=True)
    built_by = Column(String(256))
    created = Column(DateTime, index=True)
    modified = Column(DateTime, index=True)
    signed = Column(Boolean(), default=False)
    size = Column(Integer, default=0)
    checksum = Column(String(256))

    project_id = Column(Integer, ForeignKey('projects.id'))
    project = relationship('Project', backref=backref('binaries', lazy='dynamic'))

    repo_id = Column(Integer, ForeignKey('repos.id'))
    repo = relationship('Repo', backref=backref('binaries', lazy='dynamic'))

    allowed_keys = [
        'path',
        'distro',
        'distro_version',
        'arch',
        'ref',
        'built_by',
        'size',
    ]

    def __init__(self, name, project, repo=None, **kw):
        self.name = name
        self.project = project
        now = datetime.datetime.utcnow()
        self.created = now
        self.modified = now
        for key in self.allowed_keys:
            if key in kw.keys():
                setattr(self, key, kw[key])
        self.repo = repo or self._get_or_create_repo()

    def _get_or_create_repo(self):
        """
        A repo model object may exist for this binary, if it exists, then
        return it otherwise create it and then return it.
        """
        # try to find one that matches our needs first
        repo = Repo.query.filter_by(
            ref=self.ref,
            distro=self.distro,
            distro_version=self.distro_version,
            project=self.project).first()

        # create one otherwise
        if not repo:
            repo = Repo(
                self.project,
                self.ref,
                self.distro,
                self.distro_version
            )

        return repo

    def __repr__(self):
        try:
            return '<Binary %r>' % self.name
        except DetachedInstanceError:
            return '<Binary detached>'

    def update_from_json(self, data):
        """
        We received a JSON blob with updated metadata information
        that needs to update some fields
        """
        for key in self.allowed_keys:
            if key in data.keys():
                setattr(self, key, data[key])

    @property
    def last_changed(self):
        if self.modified > self.created:
            last = self.modified
        else:
            last = self.created
        return util.last_seen(last)

    def __json__(self):
        return dict(
            name=self.name,
            created=self.created,
            modified=self.modified,
            signed=self.signed,
            size=self.size,
            path=self.path,
            last_changed=self.last_changed,
            built_by=self.built_by,
            distro=self.distro,
            distro_version=self.distro_version,
            checksum=self.checksum,
            arch=self.arch,
            ref=self.ref,
        )


# Listeners


def generate_checksum(mapper, connection, target):
    try:
        target.path
    except AttributeError:
        target.checksum = None
        return

    # FIXME
    # sometimes we can accept binaries without a path and that is probably something
    # that should not happen. The core purpose of this binary is that it works with
    # paths and files, this should be required.
    if not target.path:
        return
    chsum = hashlib.sha512()
    with open(target.path) as f:
        for chunk in iter(lambda: f.read(4096), ""):
            chsum.update(chunk)
        target.checksum = chsum.hexdigest()


def update_timestamp(mapper, connection, target):
    """
    Automate the 'modified' attribute when a binary changes
    """
    target.modified = datetime.datetime.utcnow()


# listen for checksum changes
listen(Binary, 'before_insert', generate_checksum)
listen(Binary, 'before_update', generate_checksum)


# listen for timestamp modifications
listen(Binary, 'before_insert', update_timestamp)
listen(Binary, 'before_update', update_timestamp)
