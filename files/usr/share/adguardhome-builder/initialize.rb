#!/usr/bin/ruby
# Ruby + ruby-yaml 已由 OpenClash 引入；musl crypt 支持 bcrypt，无需额外密码工具。
require 'yaml'

abort 'usage: initialize.rb TEMPLATE CONFIG CREDENTIALS' unless ARGV.length == 3
template, config_path, credentials_path = ARGV
abort 'refusing to replace an existing AdGuard Home configuration' if File.exist?(config_path)

File.umask(0o077)
password = File.binread('/dev/urandom', 24).unpack1('H*')
salt = '$2a$10$' + [File.binread('/dev/urandom', 16)].pack('m0').tr('+', '.')[0, 22]
hash = password.crypt(salt)
abort 'bcrypt is unavailable' unless hash.start_with?('$2a$10$') && hash.length == 60

config = YAML.load_file(template)
config['users'] = [{ 'name' => 'admin', 'password' => hash }]
# 先保存凭据，再发布配置。异常中断后可重跑，但绝不覆盖已发布的配置。
File.open(credentials_path, 'w', 0o600) do |file|
  file.write("Username: admin\nPassword: #{password}\n")
end
File.chmod(0o600, credentials_path)
tmp = "#{config_path}.tmp"
File.open(tmp, 'w', 0o600) { |file| file.write(YAML.dump(config)) }
File.rename(tmp, config_path)
