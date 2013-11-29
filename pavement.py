from __future__ import print_function

import os
from optparse import make_option
import urlparse

from jinja2 import BaseLoader, Environment, TemplateNotFound
import paramiko
from paver.easy import *
import yaml


@task
@cmdopts([("host=", None, "The host for which to build")], share_with=['generate_image'])
def upgrade(options):
    call_task('generate_config', options={
        'host': options.host})
    call_task('generate_image', options={
        'host': options.host})
    call_task('deploy', options={
        'host': options.host})

@task
@cmdopts([("host=", None, "The host for which to build")], share_with=['generate_image'])
def generate_config(options):
    """
    Read the template files and write out the custom config of a host
    """
    # template name -> file mode
    config_file_templates = {}

    config = get_config(options.host)
    target_dir = path('target')

    for parent_files_dir in filter(lambda p: p.exists(),
            [target_dir.joinpath(p, 'files') for p in config['parents']]):
        for config_file in parent_files_dir.walkfiles():
            template_name = parent_files_dir.relpathto(config_file)
            if template_name not in config_file_templates:
                config_file_templates[template_name] = config_file.lstat()

    # Load Jinja Environment
    template_env = Environment(loader=ConfigdichLoader(target_dir))

    build_dir = path('config').joinpath(options.host)
    # Clean out the build dir
    build_dir.rmtree()
    build_dir.makedirs_p()

    for config_file_name, template_file_stat in config_file_templates.items():
        rendered_config_file_path = build_dir.joinpath(config_file_name)
        # Create the directory that the config file will be rendered to in if needed
        rendered_config_file_path.dirname().makedirs_p()
        # Render the template to the file
        t = template_env.get_template(options.host + "/" + str(config_file_name))
        rendered_config_file_path.write_text(t.render(config))
        rendered_config_file_path.chmod(template_file_stat.st_mode)

@task
# Configuration must be generated prior to building the image for the same host
@needs('generate_config')
@cmdopts([("host=", None, "The host for which to build")])
def generate_image(options):
    """
    Generate the image for installation on a machine.
    """
    #call_task(generate_config, options=options)
    config = get_config(options.host)
    build_dir = path('build')
    # Create the build directory if needed
    build_dir.makedirs_p()

    host_config_files_path = path('config').joinpath(options.host).abspath()
    host_image_path = path('images').joinpath(options.host).abspath()
    # Create images directory if needed
    host_image_path.makedirs_p()

    # Build the custom image for this machine including the custom package
    # list and configfiles.
    #image_builder_tar_path = get_image_builder(config)
    with pushd(build_dir):
        if not path('openwrt').exists():
            sh('git clone git://git.openwrt.org/openwrt.git')
        with pushd('openwrt'):
            try:
                sh('./scripts/feeds update packages')
                sh('./scripts/feeds install -a -p packages')
                path.copytree(host_config_files_path, 'files')
                path('files/buildroot-config').move('.config')
                sh('make defconfig')
                sh('make prereq')
                sh('make -j5 # V=s')

                # Copy image to target location
                built_image_path = path('bin').walkfiles(config['openwrt_image_builder_image_filename']).next()
                built_image_path.copy(host_image_path)
            finally:
                path('files').rmtree()
                path('.config').remove()

@task
@cmdopts([("host=", None, "The host for which to build")])
def deploy(options):
    """
    Deploy a bundled image to a machine and install it via sysupgrade.
    """
    config = get_config(options.host)
    local_host_image_path = path('images').joinpath(options.host, config['openwrt_image_builder_image_filename'])
    remote_host_image_path = path('/tmp').joinpath(config['openwrt_image_builder_image_filename'])
    # Use SCP because paramiko SFTP does not seem to play nice with dropbear
    sh("scp " + local_host_image_path + " root@" + options.host + ":" + remote_host_image_path)

    # Connect to machine and install image.
    # Wait until the system says it is rebooting, then disconnect. The
    # connection will not be closed by remote so we have to take care of
    # it or we will run into a timeout.
    info("Performing system upgrade...")
    ssh = paramiko.SSHClient()
    # TODO: Add a list of trusted hostkeys
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(options.host, username='root')
    stdin, stdout, stderr = ssh.exec_command("sysupgrade -n -v " + remote_host_image_path)
    while True:
        read_line = stdout.readline()
        print(read_line, end="")
        if "Rebooting system..." in read_line:
            ssh.close()
            break

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


def get_image_builder(config):
    """
    Get the path to the tar file containing the image builder.

    This function will download and unpack the image builder tar if it
    is not yet available.
    """
    builder_uri = config['openwrt_image_builder_uri']
    # Use the last path component of the URI as the filename
    builder_filename = path(urlparse.urlparse(builder_uri).path).name
    # Strip off the bz2 extension
    builder_tar_filename = builder_filename.namebase
    dl_dir = path('/tmp/configdich/downloads')
    builder_tar_path = dl_dir.joinpath(builder_tar_filename)
    dl_path = dl_dir.joinpath(builder_filename)
    if builder_tar_path.exists():
        # Everything already done
        pass
    elif dl_path.exists():
        # Image downloaded but not unpacked
        sh("bunzip2 {0}".format(dl_path))
    else:
        dl_dir.makedirs_p()
        # Download image
        sh('wget -c -O {0} {1}'.format(dl_path, builder_uri))
        # Unpack image
        sh("bunzip2 {0}".format(dl_path, builder_filename))
    return builder_tar_path

class ConfigdichLoader(BaseLoader):
    """
    Template loader to support loading configuration file templates from other targets using the pseudo-path description
    [target]/[config_file_path].
    """

    def __init__(self, target_path):
        self.target_path = target_path

    def get_source(self, environment, template):
        # split the template identifier into target an template path at
        # the first /
        target, relative_template_path = template.split("/", 1)

        target_template_path = self.target_path.joinpath(target, 'files', relative_template_path)
        # Check if the template file exists for the specified target
        if target_template_path.exists():
            old_mtime = target_template_path.mtime
            # Return the template source to the caller
            return target_template_path.text(), target_template_path, lambda: old_mtime == target_template_path.mtime
        else:
            # The template file does not exist, check if it exists in the parent target
            parent_target = get_config(target)['parent']
            if parent_target is not None:
                return self.get_source(environment, parent_target + "/" + relative_template_path)
            else:
                raise TemplateNotFound(template)
