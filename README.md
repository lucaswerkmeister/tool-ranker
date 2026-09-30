# Ranker

[Ranker](https://ranker.toolforge.org/) is a tool to edit the rank of several Wikidata statements at once.

For more information,
please see the tool’s [on-wiki documentation page](https://www.wikidata.org/wiki/User:Lucas_Werkmeister/Ranker).

## Toolforge setup

On Wikimedia Toolforge, this tool runs under the `ranker` tool name,
using the [Toolforge Components Service](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Deploy_your_tool) to coordinate
building a container with the [Toolforge Build Service](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Build_Service)
and then deploying that for the webservice.
The components configuration is in the `toolforge.yaml` file.

To start a new deployment,
run the following command on Toolforge after becoming the tool account:

```sh
toolforge components deployment create
```

This should automatically kick off an image build and restart the webservice at the end.

### Details and troubleshooting

To inspect the overall deployment status, run:

```sh
toolforge components deployment show
```

To debug the image build step, it may be useful to trigger an image build explicitly –
you can add `--ref=foobar` to build from the `foobar` branch instead of the `main` branch:

```sh
toolforge build start https://gitlab.wikimedia.org/toolforge-repos/ranker
```

The web frontent is a Flask WSGI app using gunicorn,
and runs as the `ranker` job,
which you may inspect with commands like these:

```sh
toolforge jobs show ranker
toolforge jobs logs ranker
kubectl get deployment ranker
kubectl exec -it deployment/ranker -- bash
```

### Configuration

The tool reads configuration from both the `config.yaml` file (if it exists)
and from any environment variables starting with `TOOL_*`.
The config file is more convenient for local development;
the environment variables are used on Toolforge:
list them with `toolforge envvars list`.
Nested dicts are specified with envvar names where `__` separates the key components,
so that e.g. the following are equivalent:

```sh
toolforge envvars create TOOL_OAUTH__CLIENT_ID 7b31f63d74b5952c43d4df2b7d085a4f
```

```yaml
OAUTH:
    CLIENT_ID: 7b31f63d74b5952c43d4df2b7d085a4f
```

For the available configuration variables, see the `config.yaml.example` file.

### Update

To update the tool, build a new version of the image as described above,
then restart the webservice:

```sh
toolforge build start --use-latest-versions https://gitlab.wikimedia.org/toolforge-repos/ranker
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
