pool, (system, sales, op1, op2, contractor, engineer) = DIAGRAM.add_pool(
    ROOT_PROCESS_ID,
    ['Система мониторинга', 'Энергосбыт', 'Оператор 1 линии', 'Оператор 2 линии', 'Подрядчик связи', 'Инженер-метролог']
)

source_gate = DIAGRAM.add_exclusive_gateway('Автоматическое создание?', system)
auto_create = DIAGRAM.add_script_task('Создать заявку (авто)', system)
manual_create = DIAGRAM.add_user_task('Создать заявку вручную', op1)

DIAGRAM.add_link(ROOT_START_TASK_ID, source_gate)
DIAGRAM.add_link(source_gate, auto_create, name='да')
DIAGRAM.add_link(source_gate, manual_create, name='нет')

knowledge = DIAGRAM.add_user_task('Поиск решения в базе знаний', op1)
DIAGRAM.add_link(auto_create, knowledge)
DIAGRAM.add_link(manual_create, knowledge)

resolve_gate = DIAGRAM.add_exclusive_gateway('Решено за 30 мин?', op1)
resolved = DIAGRAM.add_script_task('Закрыть заявку', op1)
escalate = DIAGRAM.add_user_task('Эскалировать заявку', op1)

DIAGRAM.add_link(knowledge, resolve_gate)
DIAGRAM.add_link(resolve_gate, resolved, name='да')
DIAGRAM.add_link(resolve_gate, escalate, name='нет')
DIAGRAM.add_link(resolved, ROOT_END_TASK_ID)

diagnose = DIAGRAM.add_user_task('Диагностировать проблему', op2)
DIAGRAM.add_link(escalate, diagnose)

split = DIAGRAM.add_parallel_gateway('', op2)
DIAGRAM.add_link(diagnose, split)

notify = DIAGRAM.add_user_task('Уведомить энергосбыт о неполных данных', sales)
type_gate = DIAGRAM.add_exclusive_gateway('Тип проблемы?', op2)

DIAGRAM.add_link(split, notify)
DIAGRAM.add_link(split, type_gate)

comm_issue = DIAGRAM.add_user_task('Привлечь подрядчика связи', contractor)
equip_issue = DIAGRAM.add_user_task('Выезд инженера-метролога', engineer)

DIAGRAM.add_link(type_gate, comm_issue, name='каналы связи')
DIAGRAM.add_link(type_gate, equip_issue, name='оборудование')

join = DIAGRAM.add_parallel_gateway('', op2)
DIAGRAM.add_link(comm_issue, join)
DIAGRAM.add_link(equip_issue, join)
DIAGRAM.add_link(notify, join)

recalc = DIAGRAM.add_script_task('Досчитать данные', system)
DIAGRAM.add_link(join, recalc)

close2 = DIAGRAM.add_script_task('Закрыть заявку', op2)
DIAGRAM.add_link(recalc, close2)
DIAGRAM.add_link(close2, ROOT_END_TASK_ID)