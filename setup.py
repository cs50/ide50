from setuptools import setup

setup(
    author="CS50",
    author_email="sysadmins@cs50.harvard.edu",
    classifiers=[
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development"
    ],
    message_extractors = {
        'ide50': [('**.py', 'python', None),],
    },
    description="This is CS50 CLI, with which you can mount a directory inside of an Ubuntu container.",
    license="GPLv3",
    install_requires=["inflect", "requests"],
    keywords="ide50",
    name="ide50",
    python_requires=">=3.6",
    packages=["ide50"],
    entry_points={
        "console_scripts": ["ide50=ide50.__main__:main"]
    },
    url="https://github.com/cs50/ide50",
    version="1.0.0",
    include_package_data=True
)
