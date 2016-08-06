import React from 'react';
import autobind from 'autobind-decorator';


function toggle( props ) {
  const { status = {} } = props;
  props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: status.running ? 'stop' : 'start' } 
      }, props.cell.get_callbacks() );
}

function DisplayStatus( props ) {
    const { status = {} } = props;
    const action = status.running ? 'Stop' : 'Start';
    const running = status.running ? 'Running' : 'Stopped';

    return ( 
      <div id="timbr_machine_status">
        <div style={{'float': 'right'}}>
          <button className='btn-default' onClick={ () => toggle( props ) }>{ action }</button>
        </div>
        <div className="timbr-header">
          <span className="timbr-title">Timbr Machine Status ({running})</span>
        </div>
        <div>
          <span className='field-name'>Processed: </span><span className='field-stat'> { status.processed } </span>
        </div>
        <div>
          <span className='field-name'>Errors: </span><span className='field-stat'> { status.errored } </span>
        </div>
        <div>
          <span className='field-name'>Queue Length: </span><span className='field-stat'> { status.queue_size } </span>
        </div>
      </div>
    );
}

export default DisplayStatus;
