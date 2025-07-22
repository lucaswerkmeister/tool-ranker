# Ranker

[Ranker](https://ranker.toolforge.org/) is a tool to edit the rank of several Wikidata statements at once.

For more information,
please see the tool’s [on-wiki documentation page](https://www.wikidata.org/wiki/User:Lucas_Werkmeister/Ranker).

## Toolforge setup

On Wikimedia Toolforge, this tool runs under the `ranker` tool name.
Source code resides in `~/www/python/src/`,
a virtual environment is set up in `~/www/python/venv/`,
logs end up in `~/uwsgi.log`.

If the web service is not running for some reason, run the following command:
```
webservice start
```
If it’s acting up, try the same command with `restart` instead of `start`.
Both should pull their config from the `service.template` file,
which is symlinked from the source code directory into the tool home directory.

To update the service, run the following commands after becoming the tool account:
```
webservice shell
source ~/www/python/venv/bin/activate
cd ~/www/python/src
git fetch
git diff @ @{u} # inspect changes
git merge --ff-only @{u}
pip-sync
webservice restart
```

## Local development setup

You can also run the tool locally, which is much more convenient for development
(for example, Flask will automatically reload the application any time you save a file).

```
git clone https://gitlab.wikimedia.org/toolforge-repos/ranker.git
cd tool-ranker
pip3 install -r requirements.txt -r dev-requirements.txt
FLASK_APP=app.py FLASK_ENV=development flask run
```

If you want, you can do this inside some virtualenv too.

## Contributing

To send a patch, you can submit a
[pull request on GitHub](https://github.com/lucaswerkmeister/tool-ranker) or a
[merge request on GitLab](https://gitlab.wikimedia.org/toolforge-repos/ranker).
(E-mail / patch-based workflows are also acceptable.)

## License

The code in this repository is released under the AGPL v3, as provided in the `LICENSE` file.
