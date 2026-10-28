"""Check the generator and real udev matching without administrator writes."""
import grp,importlib.util,os,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('access',root/'prepare_cpu_power_access.py');access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)
for group in ('', 'bad name', 'x;id', 'x/../../root', 'x"', '-x', 'x\nRUN+=bad'):
    try:access.rules_for(group)
    except ValueError:pass
    else:raise AssertionError(group)
with tempfile.TemporaryDirectory(prefix='.nova-power-access-',dir=root) as folder:
    folder=pathlib.Path(folder);group=grp.getgrgid(os.getgid()).gr_name
    access.prepare(folder/'prepared',group)
    rule=folder/'prepared'/access.RULE_NAME
    text=rule.read_text();assert text.count('RUN+=')==2
    assert 'ACTION=="add|change"' in text and 'SUBSYSTEM=="powercap"' in text and 'ATTR{name}=="package-*"' in text
    assert '/sys%p/energy_uj' in text and 'chmod g+r' in text
    assert not any(s in text for s in ('constraint_', 'power_limit', 'enabled=', 'chmod a+', 'chmod o+'))
    access.prepare(folder/'prepared',group)
    rule.write_text('changed')
    try:access.prepare(folder/'prepared',group)
    except ValueError:pass
    else:raise AssertionError('Changed output overwritten')
    rule.unlink();rule.symlink_to(folder/'elsewhere')
    try:access.prepare(folder/'prepared',group)
    except ValueError:pass
    else:raise AssertionError('Output symlink followed')
    prepared=access.prepare(folder/'matching',group)
    package=pathlib.Path('/sys/class/powercap/intel-rapl:0')
    if package.exists():
        for action in ('add','change'):
            result=subprocess.run(['udevadm','test','--action='+action,'--extra-rules-dir='+str(prepared),str(package)],capture_output=True,text=True)
            output=result.stdout+result.stderr
            assert '/usr/bin/chgrp '+group+' /sys/devices/' in output,output
            assert '/usr/bin/chmod g+r /sys/devices/' in output,output
        core=pathlib.Path('/sys/class/powercap/intel-rapl:0:0')
        if core.exists():
            result=subprocess.run(['udevadm','test','--action=add','--extra-rules-dir='+str(prepared),str(core)],capture_output=True,text=True)
            assert '/usr/bin/chgrp '+group+' /sys/devices/' not in result.stdout+result.stderr
print('Safe group input, shell/rule syntax, output preservation, package-only add/change matching and subdomain exclusion passed.')
