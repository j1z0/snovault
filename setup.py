import os
import sys
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

requires = [
    'Pillow',
    'PyBrowserID',
    'SQLAlchemy>=1.0.0b1',
    'WSGIProxy2',
    'WebTest',
    'boto',
    'botocore',
    'jmespath',
    'boto3',
    'elasticsearch',
    'lucenequery',
    'future',
    'humanfriendly',
    'jsonschema_serialize_fork',
    'loremipsum',
    'netaddr',
    'passlib',
    'psutil',
    'pyramid',
    'pyramid_localroles',
    'pyramid_multiauth',
    'pyramid_tm',
    'python-magic',
    'pytz',
    'rdflib',
    'rdflib-jsonld',
    'rfc3987',
    'setuptools',
    'simplejson',
    'strict_rfc3339',
    'subprocess_middleware',
    'xlrd',
    'zope.sqlalchemy',
]

if sys.version_info.major == 2:
    requires.extend([
        'backports.functools_lru_cache',
        'subprocess32',
    ])

tests_require = [
    'pytest>=2.4.0',
    'pytest-bdd',
    'pytest-mock',
    'pytest-splinter',
    'pytest_exact_fixtures',
]

setup(
    name='snovault',
    version='0.1',
    description='Metadata database for ENCODE',
    long_description=README + '\n\n' + CHANGES,
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    zip_safe=False,
    author='Laurence Rowe',
    author_email='hitz@stanford.edu',
    url='http://snovault.org',
    license='MIT',
    install_requires=requires,
    tests_require=tests_require,
    extras_require={
        'test': tests_require,
    },
    entry_points='''
        [console_scripts]
        batchupgrade = snovault.batchupgrade:main
        create-mapping = snovault.elasticsearch.create_mapping:main
        dev-servers = snovault.dev_servers:main
        es-index-listener = snovault.elasticsearch.es_index_listener:main

        add-date-created = snovault.commands.add_date_created:main
        check-rendering = snovault.commands.check_rendering:main
        deploy = snovault.commands.deploy:main
        extract_test_data = snovault.commands.extract_test_data:main
        es-index-data = snovault.commands.es_index_data:main
        import-data = snovault.commands.import_data:main
        jsonld-rdf = snovault.commands.jsonld_rdf:main
        migrate-files-aws = snovault.commands.migrate_files_aws:main
        profile = snovault.commands.profile:main
        spreadsheet-to-json = snovault.commands.spreadsheet_to_json:main
        migrate-attachments-aws = snovault.commands.migrate_attachments_aws:main
        migrate-dataset-type = snovault.commands.migrate_dataset_type:main

        [paste.app_factory]
        main = snovault:main

        [paste.composite_factory]
        indexer = snovault.elasticsearch.es_index_listener:composite

        [paste.filter_app_factory]
        memlimit = snovault.memlimit:filter_app
        ''',
)
