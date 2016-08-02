import React from 'react';
import dispatcher from './dispatcher.js';
import autobind from 'autobind-decorator';

class DisplayStatus extends React.Component {

  constructor( props ) {
    super( props );
    this.state = { 
      status: {}
    };
  }

  toggle() {
    this.props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: this.state.status.running ? 'stop' : 'start' } 
      }, this.props.cell.get_callbacks() );
  }

  componentWillMount(){
    dispatcher.register( payload => {
      if ( payload.actionType === 'display_update' ) {
        this.setState({ status: payload.data.status })
      }
    } );
  }

  @autobind
  handleTabSelect(index, last) {
    console.log('Selected tab: ' + index + ', Last tab: ' + last);
  }

  render() {
    const { status } = this.state;

    const action = status.running ? 'Stop' : 'Start';
    const running = status.running ? 'Running' : 'Stopped';

    return ( 
      <div id="timbr_machine_status">
        <div style={{'float': 'right'}}>
          <button className='btn-default' onClick={ () => this.toggle.apply(this) }>{ action }</button>
        </div>
        <div className="timbr-header">
          <span className="timbr-title">Timbr Machine ({running})</span>
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
}

export default DisplayStatus;
