from __future__ import print_function

import os
import paramiko
import sys
import urlparse
import yaml

from fabric.api import env, hide, lcd, local, parallel
from jinja2 import BaseLoader, Environment, TemplateNotFound

# TODO:
# - Add .fabricrc options like build_directory and download_directory to README

env.hosts = []
env.user = "root"


### Fabric tasks###


@parallel
def generate_config():
    """
    Read the template files and write out the custom config of an AP
    """
    # Get a list of all files that shall be rendered
    file_set = set()
    __cwd__ = os.path.dirname(__file__)
    config = get_config(env.host_string)
    basepath = os.path.join(__cwd__, 'target')
    for parent in config['parents']:
        cwd = os.path.join(basepath, parent, 'files')
        for root, subFolders, files in os.walk(cwd):
                for file in files:
                    file_set.add(os.path.join(root, file).replace(cwd, ''))
    builddir = os.path.join(__cwd__, 'config', env.host_string)
    # Load Jinja Environment
    template_env = Environment(loader=ConfigdichLoader(basepath))
    # Create output directory if it does not exist
    local('mkdir -p {0}'.format(builddir))
    # Render each file and ensure its output diretory exists
    for file in file_set:
        filepath = file.lstrip('/')
        outfilename = os.path.join(builddir, filepath)
        local('mkdir -p {0}'.format(os.path.dirname(outfilename)))
        print('[localhost] write: {1}'.format(env.host_string, outfilename))
        output = open(outfilename, 'w')
        t = template_env.get_template(os.path.join(env.host_string, filepath))
        output.write(t.render(config))
        output.close()


@parallel(pool_size=5)
def generate_image():
    """
    Generate the image for installation on a machine.
    """
    host = env.host_string
    config = get_config(host)
    build_directory = getattr(env, 'build_directory', '/tmp/fabric/build')
    build_directory = os.path.join(build_directory, 'configdich')

    host_files_path = os.path.realpath(os.path.join("config", host))
    host_images_path = os.path.realpath(os.path.join("images", host))
    local('mkdir -p {0}'.format(host_images_path))

    # Build up the custom package list for opkg
    host_packages_string = ''
    for package in config['opkg_packages']:
        host_packages_string += package + "  "
    for package in config['opkg_omit_packages']:
        host_packages_string += "-" + package + "  "

    # Build the custom image for this machine including the custom package
    # list and configfiles.
    image_builder_tar_location = get_image_builder(config)
    image_builder_tar_filename = os.path.split(image_builder_tar_location)[1]
    local('mkdir -p {0}'.format(build_directory))
    with lcd(build_directory):
        local("mkdir -p " + env.host_string)
        with lcd(env.host_string):
            local("tar xf {0}".format(image_builder_tar_location))
            with lcd(image_builder_tar_filename.rstrip(".tar")):
                with hide('output'):
                    # Build image
                    cmd = 'make image FILES="{0}" PACKAGES="{1}"'
                    cmd = cmd.format(host_files_path, host_packages_string)
                    local(cmd)
                # Copy image to target location
                filename = config['openwrt_image_builder_image_filename']
                image_source_path = os.path.join('bin', '*', filename)
                local('cp {0} {1}'.format(image_source_path, host_images_path))
        local("rm -rf " + env.host_string)


def deploy():
    """
    Deploy a bundled image to a machine and install it via sysupgrade.
    """
    config = get_config(env.host_string)
    local_host_image_path = os.path.realpath(os.path.join("images", env.host_string,
        config['openwrt_image_builder_image_filename']))
    remote_host_image_path = os.path.realpath(os.path.join("/tmp", config['openwrt_image_builder_image_filename']))
    # Use SCP because paramiko SFTP does not seem to play nice with dropbear
    with hide('output'):
        local("scp " + local_host_image_path + " root@" + env.host + ":" + remote_host_image_path)

    # Connect to machine and install image.
    # Wait until the system says it is rebooting, then disconnect. The
    # connection will not be closed by remote so we have to take care of
    # it or we will run into a timeout.
    print("[{}] Performing system upgrade...".format(env.host_string))
    ssh = paramiko.SSHClient()
    # TODO: Add a list of trusted hostkeys
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(env.host, username=env.user)
    stdin, stdout, stderr = ssh.exec_command("sysupgrade -n -v " + remote_host_image_path)
    while True:
        read_line = stdout.readline()
        print(read_line, end="")
        if "Rebooting system..." in read_line:
            ssh.close()
            break

### Utility functions ###


def get_image_builder(config):
    """
    Get the path to the tar file containing the image builder.

    This function will download and unpack the image builder tar if it
    is not yet available.
    """
    builder_uri = config['openwrt_image_builder_uri']
    # Use the last path component of the URI as the filename
    builder_filename = os.path.split(urlparse.urlparse(builder_uri).path)[1]
    builder_tar_filename = builder_filename.rstrip(".bz2")
    dl_directory = getattr(env, 'download_directory', '/tmp/fabric/downloads')
    dl_directory = os.path.join(dl_directory, 'configdich')
    builder_tar_location = os.path.join(dl_directory, builder_tar_filename)
    dl_location = os.path.join(dl_directory, builder_filename)
    if os.path.exists(builder_tar_location):
        # Everything already done
        pass
    elif os.path.exists(dl_location):
        # Image downloaded but not unpacked
        local("bunzip2 {0}".format(dl_location))
    else:
        local('mkdir -p {0}'.format(dl_directory))
        # Download image
        local('wget -c -O {0} {1}'.format(dl_location, builder_uri))
        # Unpack image
        local("bunzip2 {0}".format(dl_location, builder_filename))
    return builder_tar_location


def get_config(target):
    """
    Load the configuration for a specific target and include all parent
    configuration values.
    """
    config = yaml.load(file("target/{}/config.yml".format(target)))
    if 'parent' in config.keys():
        config = dict(get_config(config['parent']).items() + config.items())

    if 'parents' not in config:
        config['parents'] = []
    config['parents'].append(target)

    return config


class ConfigdichLoader(BaseLoader):
    def __init__(self, target_path):
        self.target_path = target_path

    def get_source(self, environment, template):
        # split the template identifier into target an template path at
        # the first /
        target, template_path = template.split("/", 1)

        # If the template path is absolute, make it relative
        template_path = template_path.lstrip('/')

        current_target_template_path = os.path.join(self.target_path, target, 'files', template_path)
        # Check if the template file exists for the specified target
        if os.path.exists(os.path.join(current_target_template_path)):
            mtime = os.path.getmtime(current_target_template_path)
            with file(current_target_template_path) as f:
                source = f.read().decode('utf-8')
            # Return the template source to the caller
            return source, current_target_template_path, lambda: mtime == os.path.getmtime(current_target_template_path)
        # The template file does not exist, check if it exists in the parent target
        else:
            parent_target = get_config(target)['parent']
            if parent_target is not None:
                return self.get_source(environment, parent_target + "/" + template_path)
            else:
                raise TemplateNotFound(template)
