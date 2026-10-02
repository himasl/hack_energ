pool, (scada, dispatcher, crew, repair_crew) = DIAGRAM.add_pool(ROOT_PROCESS_ID, ['SCADA', 'Диспетчер', 'Оперативная бригада', 'Ремонтная бригада'])

receive_signal = DIAGRAM.add_script_task('Получить сигнал аварии', scada)
register_event = DIAGRAM.add_script_task('Зарегистрировать событие', scada)
evaluate = DIAGRAM.add_user_task('Оценить ситуацию', dispatcher)
dispatch_crew = DIAGRAM.add_user_task('Направить оперативную бригаду', dispatcher)

crew_out = DIAGRAM.add_user_task('Выезд на место', crew)
inspect = DIAGRAM.add_user_task('Осмотреть участок', crew)
disconnect = DIAGRAM.add_user_task('Отключить повреждённый участок', crew)
ground = DIAGRAM.add_user_task('Установить заземление', crew)

restore_gateway = DIAGRAM.add_exclusive_gateway('Восстановить питание по резервной схеме?', crew)
switch_power = DIAGRAM.add_script_task('Переключить питание', crew)
call_repair = DIAGRAM.add_user_task('Вызвать ремонтную бригаду', crew)

repair_task = DIAGRAM.add_user_task('Устранить повреждение', repair_crew)

check_power = DIAGRAM.add_script_task('Проверить питание', crew)
power_gateway = DIAGRAM.add_exclusive_gateway('Питание восстановлено?', crew)

record_journal = DIAGRAM.add_user_task('Оформить запись в журнале', dispatcher)
close_event = DIAGRAM.add_script_task('Закрыть событие', scada)

DIAGRAM.add_link(ROOT_START_TASK_ID, receive_signal)
DIAGRAM.add_link(receive_signal, register_event)
DIAGRAM.add_link(register_event, evaluate)
DIAGRAM.add_link(evaluate, dispatch_crew)
DIAGRAM.add_link(dispatch_crew, crew_out)
DIAGRAM.add_link(crew_out, inspect)
DIAGRAM.add_link(inspect, disconnect)
DIAGRAM.add_link(disconnect, ground)
DIAGRAM.add_link(ground, restore_gateway)

DIAGRAM.add_link(restore_gateway, switch_power, name='да')
DIAGRAM.add_link(restore_gateway, call_repair, name='нет')
DIAGRAM.add_link(switch_power, check_power)
DIAGRAM.add_link(call_repair, repair_task)
DIAGRAM.add_link(repair_task, check_power)

DIAGRAM.add_link(check_power, power_gateway)
DIAGRAM.add_link(power_gateway, record_journal, name='да')
DIAGRAM.add_link(power_gateway, inspect, name='нет')

DIAGRAM.add_link(record_journal, close_event)
DIAGRAM.add_link(close_event, ROOT_END_TASK_ID)