# configdich
## Featuring propriertary technology developed by the makers of TurboOlaf!

**configdich** is a configuration management system for medium to large-scale deployments of OpenWRT machines. By making use of templating for configuration files and the concept of inheritance for configuration options, managing a large number of OpenWRT embedded devices, each with its own distinct configuration, becomes a breeze.

## Concepts

A host configuration in *configdich* is called a *target* and lives in a subdirectory of `targets/`. A target consists of two things:
* A `config.yml` that contains meta-information that is used only by *configdich* itself as well as variables that can later be accessed in the template rendering context
* A `files/` subdirectory containing configuration file templates that are later copied to the root of the generated OpenWRT image

*configdich* uses inheritance to allow grouping similar configurations and to avoid redundancy. A child target inherits all configuration variables from its parent (although these can be overridden in the child configuration) as well as configuration files placed in `files/` (although, again, a file in the child target will override that of a parent).

[Jinja2]() is used as a template engine and also supports inheritance at the template level.

## Usage

First of all, you'll probably want to install all dependencies in one go by running `pip install -r requirements.txt`. If you don't know [`virtualenv`](http://www.virtualenv.org/) yet, drop everyting and check it out now.

The actual magic happens in `pavement.py` and relies on [Paver](http://paver.github.io/) for an easy way to perform dirty shell tricks from within Python in a way that does not look too shady from the outside. Currently, the target name and the DNS name have to be identical for automatic deployment to work.

Use `paver generate_config --host [target]` to generate configuration files for a target. The finished configuration, ready to be placed in the root of and OpenWRT filesystem, will be placed in `config/[target name>]`.

Use `paver generate_image --host [target]` to build a ready-to-flash OpenWRT image using the files built in the `generate_config` step and the package manager configuration specified by the target configuration file.

Use `paver deploy --host [target]` to copy the image built in the `generate_image` step to the target using SSH and flash it using the OpenWRT `sysupgrade` utility.

`paver upgrade --host [target]` is a shortcut that will do all three steps (generate configuration, build image, deploy) with one command.


## License and Contributions

*configdich* was initially built by [Uwe L. Korn](http://xhochy.org) and [Leon Handreke](http://leonh.ndreke.de) as a proof-of-concept in an afternoon. It is licensed under an MIT License. For more information, please see the the `COPYING` file in the project root. Contributions in all forms are most welcome!
