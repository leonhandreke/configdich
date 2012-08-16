# configdich
## Featuring propriertary technology developed by the makers of TurboOlaf!

**configdich** is a configuration management system for medium to large-scale deployments of OpenWRT machines. By making use of templating for configuration files and the concept of inheritance also known from object-oriented programming languages, managing a large number of OpenWRT embedded devices, each with its own distinct configuration, becomes a breeze. An example for such an environment would be a

## Concepts

A host configuration in *configdich* is called a *target* and lives in a subdirectory of `targets/`. A target consists of two things: a `config.yml` that contains meta-information that is used only by *configdich* itself as well as variables that can later be accessed in the template rendering context and a `files/` subdirectory containing configuration file templates that are later copied to the root of the generated OpenWRT image.

*configdich* uses inheritance to allow grouping similar configurations and to avoid redundancy. A child target inherits all configuration variables specified in `config.yml` (although these can be overridden in the child configuration) as well as configuration files placed in `files/` (although, again, a file in the child target will override that of a parent).

[Jinja2]() is used as a template engine and also supports inheritance at the template level.

Bundled with the code comes a simple example that shows how to use the mechanisms mentioned above.

## Usage

First of all, you'll probably want to install all dependencies in one go by running `pip install -r dependencies.txt`. If you don't know [`virtualenv`](http://www.virtualenv.org/) yet, drop everyting and check it out now.

The actual magic happens in `fabfile.py` and relies on [Fabric]() for an easy way to perform dirty shell tricks from within Python in a way that does not look too shady from the outside. Leaf targets (targets that will actually be built and are not just parents for other targets) can be specified using the `env.hosts` variable somewhere near the top of the file. Currently, the target name and the DNS name have to be identical for automatic deployment to work.

Use `fab generate_config [target]` to generate configuration files (optionally only for a single target `target`). The finished configuration, ready to be placed in the root of and OpenWRT filesystem, will be placed in `config/<target name>`.

Use `fab generate_image [target]` to build a ready-to-flash OpenWRT image using the files built in the `generate_config` step and the package manager configuration specified by the target configuration file.

Use `fab deploy [target]` to copy the image built in the `generate_image` step to the target using SSH and flash it using the OpenWRT `sysupgrade` utility.

## License and Contributions

*configdich* was initially built by [Uwe L. Korn](http://xhochy.org) and [Leon Handreke](http://leonh.ndreke.de) as a proof-of-concept in an afternoon. It is licensed under an MIT License. For more information, please see the the `COPYING` file in the project root. Contributions in all forms are most welcome!
